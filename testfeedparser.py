import feedparser
import os
import sys
import requests

def parse_all_tags(feed_url, output_dir):
    feed = feedparser.parse(feed_url)
    all_data = []

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for entry in feed.entries:
        entry_data = {}
        for key, value in entry.items():
           print(f"{key}: \t{value}")
        # try:
        #     image_url = entry["image"]["href"]
        #     print(image_url)
        #     # Download the image
        #     image_response = requests.get(image_url)
        #     image_filename = os.path.join(output_dir, os.path.basename(image_url))
        #     with open(image_filename, 'wb') as image_file:
        #         image_file.write(image_response.content)
        # except KeyError:
        #     pass

    #     all_data.append(entry_data)

    #     # Save each entry to a file named after the title
    #     filename = os.path.join(output_dir, f"{entry_data.get('title', 'untitled').replace(' ', '_')}.txt")
    #     with open(filename, 'w', encoding='utf-8') as file:
    #         for key, value in entry_data.items():
    #             file.write(f"{key}: {value}\n")

    # return all_data

# Example usage
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python testfeedparser.py <feed_url> <output_dir>")
        sys.exit(1)

    feed_url = sys.argv[1]
    output_dir = sys.argv[2]
    all_data = parse_all_tags(feed_url, output_dir)
