import feedparser
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TXXX, APIC
import os
from urllib.parse import urlparse
from pathlib import Path
import argparse
import xml.etree.ElementTree as ET
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import time

def get_file_hash(filename):
    """Calculates the MD5 hash of a file."""
    with open(filename, 'rb') as f:
        file_hash = hashlib.md5()
        chunk = f.read(8192)
        while chunk:
            file_hash.update(chunk)
            chunk = f.read(8192)
        return file_hash.hexdigest() 

def remove_duplicates(directory):
    """Removes duplicate JPEG files in a given directory."""
    hashes = {}
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith('.jpg'):
                filepath = os.path.join(root, file)
                file_hash = get_file_hash(filepath)
                if file_hash in hashes:
                    os.remove(filepath)
                    print(f"Removed duplicate: {filepath}")
                else:
                    hashes[file_hash] = filepath

def get_itunes_image(feed_xml):
    """Extract iTunes image URL from feed"""
    try:
        # Parse the feed XML to find iTunes image
        namespaces = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}
        root = ET.fromstring(feed_xml)
        itunes_image = root.find('.//itunes:image', namespaces=namespaces)
        if itunes_image is not None:
            return itunes_image.get('href')
    except Exception as e:
        print(f"Error parsing iTunes image: {str(e)}")
    return None

def add_cover_art(audio_file, image_file):
    """Add cover art to audio file using lame"""
    try:
        # Use lame to add cover art
        subprocess.run(['lame', '--ti', image_file, audio_file, audio_file + '.tmp'], stdout=subprocess.DEVNULL)
        os.replace(audio_file + '.tmp', audio_file)
        return True
    except Exception as e:
        print(f"Error adding cover art with lame: {str(e)}")
        return False

def download_episode(entry, output_dir, cover_art_data, cover_art_mime, podcast_title, podcast_author):
    """Download a single podcast episode and embed cover art"""
    # Find the audio file URL
    audio_url = None
    for link in entry.links:
        if 'audio' in link.get('type', ''):
            audio_url = link['href']
            break

    if not audio_url:
        print(f"No audio URL found for episode: {entry.title}")
        return

    # Generate safe filename from episode title
    filename_base = "".join(x for x in entry.title if x.isalnum() or x in (' ', '-', '_'))
    audio_filename = os.path.join(output_dir, f"{filename_base}.mp3")
    image_filename = os.path.join(output_dir, f"{filename_base}.jpg")

    # Skip if file already exists
    if os.path.exists(audio_filename):
        print(f"Skipping existing file: {audio_filename}")
        return

    print(f"Downloading: {entry.title}")

    # Download audio file
    try:
        audio_data = requests.get(audio_url)
        with open(audio_filename, 'wb') as f:
            f.write(audio_data.content)

        # Check if the MP3 file already has embedded cover art
        audio = MP3(audio_filename, ID3=ID3)
        has_cover_art = any(tag.FrameID == 'APIC' for tag in audio.tags.values())

        if has_cover_art:
            print(f"File already has embedded cover art: {audio_filename}")
        else:
            # Save cover art image if available
            if cover_art_data:
                with open(image_filename, 'wb') as img_file:
                    img_file.write(cover_art_data)
                print(f"Saved cover art as: {image_filename}")

            # Add metadata and cover art
            # Add ID3 tag if it doesn't exist
            try:
                audio.add_tags()
            except:
                pass

            # Add metadata
            audio.tags.add(TIT2(encoding=3, text=entry.title))  # Title
            audio.tags.add(TPE1(encoding=3, text=podcast_author))  # Artist
            audio.tags.add(TALB(encoding=3, text=podcast_title))  # Album
            audio.tags.add(TXXX(encoding=3, desc='Description', text=entry.get('description', '')))  # Description
            audio.tags.add(TXXX(encoding=3, desc='Link', text=entry.get('link', '')))  # Link
            audio.tags.add(TXXX(encoding=3, desc='Published Date', text=entry.get('published', '')))  # Published Date
            audio.tags.add(TXXX(encoding=3, desc='Duration', text=entry.get('itunes_duration', '')))  # Duration
            audio.tags.add(TXXX(encoding=3, desc='Episode Type', text=entry.get('itunes_episode_type', '')))  # Episode Type
            audio.tags.add(TXXX(encoding=3, desc='Season', text=str(entry.get('itunes_season', ''))))  # Season
            audio.tags.add(TXXX(encoding=3, desc='Episode', text=str(entry.get('itunes_episode', ''))))  # Episode
            audio.tags.add(TXXX(encoding=3, desc='Explicit', text=entry.get('itunes_explicit', '')))  # Explicit
            audio.tags.add(TXXX(encoding=3, desc='Keywords', text=entry.get('itunes_keywords', '')))  # Keywords
            audio.tags.add(TXXX(encoding=3, desc='Subtitle', text=entry.get('itunes_subtitle', '')))  # Subtitle
            audio.tags.add(TXXX(encoding=3, desc='Summary', text=entry.get('itunes_summary', '')))  # Summary

            # Set file creation date to publish date
            publish_date = entry.get('published')
            if publish_date:
                try:
                    publish_timestamp = time.mktime(time.strptime(publish_date, '%a, %d %b %Y %H:%M:%S %z'))
                    os.utime(audio_filename, (publish_timestamp, publish_timestamp))
                except ValueError as e:
                    print(f"Error parsing publish date: {str(e)}")
            audio.tags.add(TXXX(encoding=3, desc='Author', text=entry.get('itunes_author', podcast_author)))  # Author

            # Try to get episode number from itunes:episode
            episode_number = entry.get('itunes_episode')
            if episode_number:
                audio.tags.add(TXXX(encoding=3, desc='Episode', text=str(episode_number)))  # Episode number

            # Save metadata
            audio.save()

            # Add cover art if available
            if cover_art_data:
                add_cover_art(audio_filename, image_filename)
                print("Added cover art to file")

        print(f"Successfully processed: {entry.title}")

    except Exception as e:
        print(f"Error processing {entry.title}: {str(e)}")
        if os.path.exists(audio_filename):
            os.remove(audio_filename)

def download_podcast_episodes(rss_url, output_dir='downloads'):
    """
    Download podcast episodes from RSS feed and embed cover art.
    
    Args:
        rss_url (str): URL of the podcast RSS feed
        output_dir (str): Directory to save downloaded files
    """
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # Fetch the raw RSS feed content
    print(f"Fetching RSS feed from: {rss_url}")
    response = requests.get(rss_url)
    feed_content = response.content
    feed = feedparser.parse(feed_content)
    
    # Try to get cover art from multiple sources
    cover_art_data = None
    cover_art_mime = 'image/jpeg'
    
    # First try iTunes image
    itunes_image_url = get_itunes_image(feed_content)
    if itunes_image_url:
        print("Found iTunes cover art")
        try:
            cover_response = requests.get(itunes_image_url)
            if cover_response.status_code == 200:
                cover_art_data = cover_response.content
                cover_art_mime = cover_response.headers.get('content-type', 'image/jpeg')
        except Exception as e:
            print(f"Error downloading iTunes cover art: {str(e)}")
    
    # Fallback to regular feed image if iTunes image failed
    if not cover_art_data and hasattr(feed.feed, 'image'):
        print("Using RSS feed cover art")
        try:
            cover_response = requests.get(feed.feed.image.href)
            if cover_response.status_code == 200:
                cover_art_data = cover_response.content
                cover_art_mime = cover_response.headers.get('content-type', 'image/jpeg')
        except Exception as e:
            print(f"Error downloading RSS feed cover art: {str(e)}")
    
    if not cover_art_data:
        print("No cover art found in feed")
    i = 0

    # Get podcast metadata
    podcast_title = feed.feed.title if hasattr(feed.feed, 'title') else 'Unknown Podcast'
    podcast_author = feed.feed.author if hasattr(feed.feed, 'author') else 'Unknown Author'
    
    # Process each episode in parallel
    with ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(download_episode, entry, output_dir, cover_art_data, cover_art_mime, podcast_title, podcast_author)
            for entry in feed.entries
        ]
        for future in as_completed(futures):
            future.result()

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Download podcast episodes from an RSS feed and embed cover art'
    )
    parser.add_argument(
        'rss_url',
        help='URL of the podcast RSS feed'
    )
    parser.add_argument(
        '-o', '--output',
        default='downloads',
        help='Output directory for downloaded files (default: downloads)'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Run the download with provided arguments
    download_podcast_episodes(args.rss_url, args.output)

    remove_duplicates(args.output)

if __name__ == "__main__":
    main()
