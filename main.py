import tidalapi
import os
import json
import re
import subprocess
from pathlib import Path
from cleanup_tidal_playlists import normalize_track_name, connect_to_tidal, fetch_all_playlists, fetch_tidal_playlist_tracks
from create_rekordbox_xml import create_rekordbox_xml
from thefuzz import process

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


# Basispfade zu den Musikordnern
M4A_DIR = Path("/Users/anton/Music/Tidal/m4a")
MP3_DIR = Path("/Users/anton/Music/Tidal/mp3")
TOKEN_FILE = "tidal_session.json"

# Feste Pfade
INPUT_FOLDER = "/Users/anton/Music/Tidal/mp3/Playlists"  # Eingabeordner
OUTPUT_XML = "/Users/anton/Documents/rekordbox/antons_music.xml"  # Ausgabedatei


def convert_to_mp3(input_file, output_file):
    cmd = ["ffmpeg", "-nostdin", "-i", str(input_file), "-q:a", "2", str(output_file)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if output_file.exists():
        print(f"Erfolgreich konvertiert: {input_file} -> {output_file}")
        input_file.unlink()
        input_file.touch()  # Ersetzt die gelöschte Datei durch eine leere Datei

# delete m4a vs. tidal tracks
def get_local_tracks(folder_path, extensions):
    return {file.stem.lower() for file in folder_path.rglob("*") if file.suffix in extensions}

def compare_tracks(local_tracks, tidal_tracks):
    return {normalize_track_name(track) for track in local_tracks} - {normalize_track_name(track) for track in tidal_tracks}


def find_best_match(track_name, folder_path, extensions, threshold=80):
    """Sucht nach der besten Übereinstimmung im Ordner und gibt den tatsächlichen Dateinamen zurück."""
    all_files = [f.stem for ext in extensions for f in folder_path.glob(f"*{ext}")]
    best_match, score = process.extractOne(track_name, all_files)

    if best_match and score >= threshold:
        return best_match
    return None

def delete_unmatched_tracks(to_delete, folder_path, extensions):
    for track in to_delete:
        print(f"Suche nach: {track}")
        
        # Suche nach einer passenden Datei (auch wenn sie leicht anders heißt)
        best_match = find_best_match(track, folder_path, extensions)
        
        if best_match:
            for ext in extensions:
                file_path = folder_path / f"{best_match}{ext}"
                if file_path.exists():
                    print("Datei gefunden:", file_path)
                    print(bcolors.FAIL + f"Lösche: {file_path}" + bcolors.ENDC)
                    if input(bcolors.FAIL + "Löschen? [y/N]" + bcolors.ENDC).lower() in ['y', 'yes']:
                        file_path.unlink()


# delete mp3 files
def get_files_from_folder(folder_path, extensions):
    """Erstellt eine Liste der Dateien in einem Ordner mit bestimmten Erweiterungen."""
    return {file.stem.lower() for file in Path(folder_path).rglob("*") if file.suffix in extensions}

def delete_mp3_file(file_path):
    """Fragt den Nutzer, ob eine MP3-Datei gelöscht werden soll, und löscht sie ggf."""
    if file_path.exists():
        confirm = input(f"Soll die Datei {file_path} gelöscht werden? [y/N]: ").strip().lower()
        if confirm in ['y', 'yes']:
            file_path.unlink()
            print(f"{file_path} wurde gelöscht.")

def compare_and_delete(mp4_m4a_folder, mp3_folder):
    """Vergleicht die Dateien in den Ordnern und löscht nach Bestätigung nicht vorhandene MP3s."""
    mp4_m4a_files = get_files_from_folder(mp4_m4a_folder, {".mp4", ".m4a"})
    mp3_files = get_files_from_folder(mp3_folder, {".mp3"})
    
    missing_in_mp4_m4a = mp3_files - mp4_m4a_files
    # print(missing_in_mp4_m4a)
    
    for file_name in missing_in_mp4_m4a:
        mp3_file_path = Path(mp3_folder) / f"{file_name}.mp3"
        delete_mp3_file(mp3_file_path)



def convert_all_m4a_to_mp3():
    print(__name__)
    for input_file in list(M4A_DIR.rglob("*.m4a")) + list(M4A_DIR.rglob("*.mp4")):
        relative_path = input_file.relative_to(M4A_DIR)
        output_file = MP3_DIR / relative_path.with_suffix(".mp3")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        convert_to_mp3(input_file, output_file)

def main():
    session = connect_to_tidal()
    playlists = fetch_all_playlists(session)

    for playlist in playlists:
        playlist_folder_m4a = M4A_DIR / "Playlists" / playlist.name
        if not playlist_folder_m4a.exists():
            print(bcolors.WARNING + f"playlist {playlist.name} does not exist in m4a directory" + bcolors.ENDC)
            continue
        tidal_tracks = fetch_tidal_playlist_tracks(playlist)
        # print(playlist.name)
        local_tracks_m4a = get_local_tracks(playlist_folder_m4a, {'.m4a', '.mp4'})
        # print(tidal_tracks)
        # print(local_tracks_m4a)
        to_delete_m4a = compare_tracks(local_tracks_m4a, tidal_tracks)
        # print(to_delete_m4a)
        # print("...")
        delete_unmatched_tracks(to_delete_m4a, playlist_folder_m4a, {'.m4a', '.mp4'})

        playlist_folder_mp3 = MP3_DIR / "Playlists" / playlist.name



        compare_and_delete(playlist_folder_m4a, playlist_folder_mp3)


        # local_tracks_mp3 = get_local_tracks(playlist_folder_mp3, {'.mp3'})
        # if not playlist_folder_m4a.exists():
        #     print(bcolors.WARNING + f"playlist {playlist.name} does not exist in mp3 directory" + bcolors.ENDC)
        #     continue
        # to_delete_mp3 = compare_tracks(local_tracks_mp3, local_tracks_m4a)
        # print("to_delete:")
        # print(to_delete_mp3)
        # delete_unmatched_tracks(to_delete_mp3, playlist_folder_mp3, {'.mp3'})
    convert_all_m4a_to_mp3()
    print("Synchronisation abgeschlossen.")

    create_rekordbox_xml(INPUT_FOLDER, OUTPUT_XML)

if __name__ == "__main__":
    main()
