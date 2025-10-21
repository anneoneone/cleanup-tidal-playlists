import xml.etree.ElementTree as ET
import os
import json
from mutagen import File
from mutagen.mp3 import HeaderNotFoundError


def create_rekordbox_xml(input_folder, output_file):
    """Generates Rekordbox XML from the provided input folder."""
    dj_playlists = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(dj_playlists, "PRODUCT", Name="rekordbox", Version="7.0.4", Company="AlphaTheta")
    collection = ET.SubElement(dj_playlists, "COLLECTION", Entries="0")
    playlists = ET.SubElement(dj_playlists, "PLAYLISTS")
    root_playlist_node = ET.SubElement(playlists, "NODE", Type="0", Name="ROOT", Count="0")

    track_id = 1
    total_tracks = 0
    playlist_count = 0
    track_data = {}

    def get_genre(audio_file):
        return audio_file.get("genre", [""])[0] if audio_file else ""

    def get_version(playlist_name, existing_version):
        version = ""
        if " D " in playlist_name:
            version = "Digital"
        elif " V " in playlist_name:
            version = "Vinyl"
        elif " R " in playlist_name:
            version = "Recherche"
        elif " O " in playlist_name:
            version = "Old"
        return existing_version if existing_version else version

    def process_tracks(folder_path):
        nonlocal track_id
        playlist_name = os.path.basename(folder_path)

        for filename in sorted(os.listdir(folder_path)):
            if filename.lower().endswith((".mp3", ".wav", ".flac", ".aac")):
                track_path = os.path.join(folder_path, filename)
                
                try:
                    audio_file = File(track_path, easy=True)
                    if not audio_file:
                        continue
                    
                    trackname = audio_file.get("title", ["Unbekannter Titel"])[0]
                    artist = audio_file.get("artist", ["Unknown Artist"])[0]
                    album = audio_file.get("album", ["Unknown Album"])[0]
                    genre = get_genre(audio_file)
                    version = get_version(playlist_name, "")
                except (HeaderNotFoundError, Exception):
                    continue  # Fehlerhafte oder nicht unterstützte Dateien überspringen
                
                track_key = f"{trackname}_{artist}_{album}"
                if track_key in track_data:
                    track_data[track_key]["Comments"] += f" //{playlist_name}//"
                    track_data[track_key]["Mix"] = get_version(playlist_name, track_data[track_key]["Mix"])
                else:
                    track_data[track_key] = {
                        "TrackID": str(track_id),
                        "Name": trackname,
                        "Artist": artist,
                        "Album": album,
                        "Genre": genre,
                        "Mix": version,
                        "Location": f"file://localhost/{track_path.replace(os.sep, '/')}",
                        "Comments": f"//{playlist_name}//"
                    }
                    track_id += 1

    for folder_name in sorted(os.listdir(input_folder)):
        folder_path = os.path.join(input_folder, folder_name)
        if os.path.isdir(folder_path):
            process_tracks(folder_path)

    # Tracks zur Sammlung hinzufügen
    for track_info in track_data.values():
        ET.SubElement(
            collection, "TRACK",
            TrackID=track_info["TrackID"],
            Name=track_info["Name"],
            Artist=track_info["Artist"],
            Album=track_info["Album"],
            Genre=track_info["Genre"],
            Mix=track_info["Mix"],
            Location=track_info["Location"],
            Comments=track_info["Comments"]
        )
        total_tracks += 1

    collection.set("Entries", str(total_tracks))
    root_playlist_node.set("Count", str(playlist_count))
    tree = ET.ElementTree(dj_playlists)
    tree.write(output_file, encoding="UTF-8", xml_declaration=True)

    print(f"XML generation complete! Output saved to: {output_file}")

if __name__ == "__main__":
    INPUT_FOLDER = "/Users/anton/Music/Tidal/mp3/Playlists"  # Eingabeordner
    OUTPUT_XML = "/Users/anton/Documents/rekordbox/antons_music.xml"  # Ausgabedatei
    create_rekordbox_xml(INPUT_FOLDER, OUTPUT_XML)
