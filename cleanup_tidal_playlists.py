import tidalapi
import os
import json
import re

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


# Basispfad zu den Playlists auf dem Rechner
local_playlists_folder = "/Users/anton/Music/Tidal/m4a/Playlists"
TOKEN_FILE = "tidal_session.json"  # Datei für gespeichertes Token

# Verbindung zu Tidal herstellen
def connect_to_tidal():
    # Prüfen, ob ein gespeicherter Token existiert
    if os.path.exists(TOKEN_FILE):
        print("Lade gespeichertes Token...")
        with open(TOKEN_FILE, "r") as file:
            data = json.load(file)
        session = tidalapi.Session()
        session.load_oauth_session(data["token_type"], data["access_token"], data["refresh_token"])
        
        # Prüfen, ob die Session gültig ist
        if session.check_login():
            print("Erfolgreich mit gespeicherter Session angemeldet!")
            return session
        else:
            print("Gespeicherte Session ungültig, starte neuen Login...")
    
    # Neues Login, falls kein gültiger Token vorhanden ist
    session = tidalapi.Session()
    print("Bitte scanne den QR-Code oder öffne den Link zur Anmeldung:")
    print(session.login_oauth_simple())
    
    # Warte auf Authentifizierung und prüfe den Login-Status
    for _ in range(60):  # Warte bis zu 60 Sekunden
        if session.check_login():
            print("Erfolgreich angemeldet!")
            # Speichere die Session-Daten
            save_session(session)
            return session
        else:
            time.sleep(1)  # Warte 1 Sekunde und prüfe erneut
    
    raise Exception("Anmeldung fehlgeschlagen. Timeout nach 60 Sekunden.")

# Session-Daten speichern
def save_session(session):
    data = {
        "token_type": session.token_type,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }
    with open(TOKEN_FILE, "w") as file:
        json.dump(data, file)
    print("Session-Daten gespeichert!")

import re

# Alle Playlists des Benutzers abrufen
def fetch_all_playlists(session):
    user = session.user
    playlists = user.playlists()  # Alle Playlists des Benutzers abrufen
    print(f"Gefundene Playlists: {len(playlists)}")
    return playlists

# Tracks einer Playlist abrufen
def fetch_tidal_playlist_tracks(playlist):
    print(f"Verarbeite Playlist: {playlist.name}")
    tidal_tracks = set()
    for track in playlist.tracks():  # Klammern hinzufügen, um die Methode auszuführen
        artist = track.artist.name
        title = track.name
        tidal_tracks.add(f"{artist} - {title}".lower())
    return tidal_tracks


# Songs im lokalen Ordner scannen
def get_local_tracks(folder_path):
    local_tracks = set()
    for filename in os.listdir(folder_path):
        if filename.endswith(('.mp3', '.flac', '.wav', '.aac', 'm4a')):  # Audio-Dateien filtern
            # Entferne Dateiendung und bereinige Namen
            track_name = os.path.splitext(filename)[0].strip().lower()
            local_tracks.add(track_name)
    return local_tracks


def normalize_track_name(track_name):
    """
    Normalisiert einen Tracknamen:
    - Entfernt zusätzliche Interpreten (z. B. nach einem Komma)
    - Entfernt Begriffe wie "remix", "edit", "original mix"
    - Entfernt Inhalte in Klammern und Jahreszahlen
    - Entfernt abschließende Punkte beim Interpreten und Titel
    - Harmonisiert Schreibweise und bereinigt Leerzeichen
    """
    # Zerlege den Track in "Interpret - Titel"
    parts = track_name.split(" - ", maxsplit=1)
    if len(parts) == 2:
        artist, title = parts
        # Bereinige den Interpreten (nur Hauptinterpreten)
        artist = re.sub(r"(,| feat\.| & ).*", "", artist, flags=re.IGNORECASE).strip().lower()
        
        # Entferne abschließende Punkte im Interpreten-Namen
        artist = re.sub(r"\.+$", "", artist)  

        # Entferne Inhalte in runden und eckigen Klammern (z. B. "(Remastered 2023)", "[Live]")
        title = re.sub(r"\[.*?\]|\(.*?\)", "", title, flags=re.IGNORECASE)
        
        # Entferne Jahreszahlen (z. B. "2023", "2003")
        title = re.sub(r"\b\d{4}\b", "", title)
        
        # Entferne Begriffe wie "remix", "edit", "mix", etc.
        title = re.sub(r"(remix|edit|mix|version)", "", title, flags=re.IGNORECASE)
        
        # Entferne abschließende Punkte im Titel
        title = re.sub(r"\.+$", "", title)  

        # Entferne überflüssige Leerzeichen und setze auf Kleinbuchstaben
        title = re.sub(r"\s+", " ", title).strip().lower()
        
        return f"{artist} - {title}"
    
    # Falls keine Trennung gefunden wurde, nur Tracknamen normalisieren
    return track_name.strip().lower()




def compare_tracks(local_tracks, tidal_tracks):
    """
    Vergleicht lokale und Tidal-Tracks, wobei die Namen normalisiert werden.
    Gibt die zu löschenden Tracks zurück.
    """
    normalized_local_tracks = {normalize_track_name(track) for track in local_tracks}
    normalized_tidal_tracks = {normalize_track_name(track) for track in tidal_tracks}

    # Tracks, die lokal existieren, aber nicht in Tidal
    to_delete = normalized_local_tracks - normalized_tidal_tracks
    # Tracks, die in Tidal existieren, aber nicht lokal
    unmatched_tidal = normalized_tidal_tracks - normalized_local_tracks

    if to_delete:
        # Debugging-Output
        print("Nicht in Tidal-Playlist:", to_delete)
        print("Nicht lokal gefunden:", unmatched_tidal)

    return to_delete



# Dateien löschen, die nicht in der Playlist sind
# Dateien löschen, die nicht in der Playlist sind
def delete_unmatched_tracks(local_tracks, tidal_tracks, folder_path):
    to_delete = compare_tracks(local_tracks, tidal_tracks)
    for track in to_delete:
        # Suche alle Dateiendungen durch
        for ext in ['.mp3', '.flac', '.wav', '.aac', '.m4a']:
            file_path = os.path.join(folder_path, f"{track}{ext}")
            if os.path.exists(file_path):
                print(bcolors.WARNING + f"Lösche: {file_path}" + bcolors.ENDC)
                while True:
                    Prompt = input("Löschen? [y/N]\n")
                    if Prompt in ['y', 'yes']:
                        os.remove(file_path)
                    else:
                        break
                break


# Hauptlogik
if __name__ == "__main__":
    # Schritt 1: Tidal-Session aufbauen
    session = connect_to_tidal()
    
    # Schritt 2: Alle Playlists abrufen
    playlists = fetch_all_playlists(session)
    
    # Schritt 3: Jede Playlist mit lokalem Ordner abgleichen
    for playlist in playlists:
        playlist_folder = os.path.join(local_playlists_folder, playlist.name)

        # Überspringen, wenn der lokale Ordner für die Playlist nicht existiert
        if not os.path.exists(playlist_folder):
            print(f"Lokaler Ordner für Playlist '{playlist.name}' nicht gefunden, überspringe...")
            continue
        
        # Tidal-Playlist-Tracks abrufen
        tidal_tracks = fetch_tidal_playlist_tracks(playlist)
        # print(tidal_tracks)

        # Lokale Tracks scannen
        local_tracks = get_local_tracks(playlist_folder)

        # Abgleichen und löschen
        delete_unmatched_tracks(local_tracks, tidal_tracks, playlist_folder)
    
    print("Abgleich aller Playlists abgeschlossen!")
