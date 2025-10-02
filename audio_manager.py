import threading
import time
import random
import logging
import requests
import json
from pydub import AudioSegment
from pydub.playback import play

class AudioManager:
    def __init__(self):
        self.home_team = None
        self.away_team = None
        self.home_music = {}
        self.away_music = {}
        self.playback_thread = None
        self.goalhorn_positions = {}
        # URL for the bot's mute API
        self.bot_api_url = "http://localhost:31335/api/mute"

    def clear_goalhorn_positions(self):
        self.goalhorn_positions.clear()

    def _notify_bot_to_mute(self, duration_seconds):
        """
        Sends a POST request to the bot's API to mute it for a specific duration.
        Fails gracefully if the API is not available.
        """
        if duration_seconds <= 0:
            return

        # Add a 2-second buffer to ensure the bot stays muted for the whole clip
        payload = {"duration": int(duration_seconds + 2)}
        headers = {"Content-Type": "application/json"}

        logging.info(f"Requesting bot mute for {payload['duration']} seconds.")
        try:
            # Set a short timeout to avoid hanging the script
            response = requests.post(self.bot_api_url, data=json.dumps(payload), headers=headers, timeout=1)
            if response.status_code != 200:
                logging.warning(f"API call to mute bot failed with status {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            # This catches connection errors, timeouts, etc.
            logging.warning(f"Could not connect to the bot API to request mute. Is it running? Error: {e}")

    def _play_audio(self, audio_segment, duration_ms=None, fade_out_ms=0):
        logging.info(f"Playing audio for {duration_ms}ms with {fade_out_ms}ms fade out")
        if duration_ms:
            song = audio_segment[:duration_ms]
        else:
            song = audio_segment
        if fade_out_ms:
            song = song.fade_out(fade_out_ms)
        play(song)

    def play_anthems(self):
        if not self.home_music or not self.away_music:
            logging.warning("Anthems not loaded, skipping playback")
            return

        away_anthem_info = self.away_music.get("anthem")
        home_anthem_info = self.home_music.get("anthem")

        if not away_anthem_info or not home_anthem_info:
            logging.warning("Anthem files not found, skipping playback")
            return

        def _play_sequence():
            # Mute the bot for the total duration of both anthems (70s + 70s)
            self._notify_bot_to_mute(duration_seconds=140)

            # Play away anthem
            logging.info(f"Playing away anthem: {away_anthem_info[0].songname}")
            away_song = AudioSegment.from_file(away_anthem_info[0].songname)
            self._play_audio(away_song, 70 * 1000, 5 * 1000)

            # Play home anthem
            logging.info(f"Playing home anthem: {home_anthem_info[0].songname}")
            home_song = AudioSegment.from_file(home_anthem_info[0].songname)
            self._play_audio(home_song, 70 * 1000, 5 * 1000)

            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play_sequence)
            self.playback_thread.start()

    def load_team_music(self, team_id, is_home):
        # Logic to load music for a team will go here
        pass

    def play_victory_anthem(self, team):
        music_dict = self.home_music if team == "home" else self.away_music
        team_name = self.home_team if team == "home" else self.away_team

        victory_anthem = music_dict.get("victory")
        if not victory_anthem:
            logging.warning(f"No victory anthem found for team {team_name}")
            return

        def _play():
            # Mute the bot for the duration of the victory anthem (90s)
            self._notify_bot_to_mute(duration_seconds=90)
            
            logging.info(f"Playing victory anthem for team {team_name}: {victory_anthem[0].songname}")
            song = AudioSegment.from_file(victory_anthem[0].songname)
            self._play_audio(song, 90 * 1000, 5 * 1000)
            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play)
            self.playback_thread.start()

    def play_warcry(self):
        music_dict = self.home_music if random.choice(["home", "away"]) == "home" else self.away_music
        team_name = self.home_team if music_dict is self.home_music else self.away_team

        chants = music_dict.get("chant")
        if not chants:
            logging.warning(f"No chants found for team {team_name}")
            return

        chant_to_play = random.choice(chants)

        def _play():
            song = AudioSegment.from_file(chant_to_play.songname)
            
            # Mute the bot for the actual duration of the chant
            duration_seconds = len(song) / 1000
            self._notify_bot_to_mute(duration_seconds)
            
            logging.info(f"Playing warcry for team {team_name}: {chant_to_play.songname}")
            self._play_audio(song)
            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play)
            self.playback_thread.start()

    def play_goal_sound(self, team, scorer, gamestate):
        music_dict = self.home_music if team == "home" else self.away_music
        team_name = self.home_team if team == "home" else self.away_team
        home_team_bool = team == "home"

        goal_sounds = music_dict.get(scorer.lower(), music_dict.get("goal", []))
        if not goal_sounds:
            logging.warning(f"No goal horn found for team {team_name}")
            return
        
        valid_warcry_horns = []
        valid_regular_horns = []
        for sound in goal_sounds:
            for condition in sound.all: condition.home = home_team_bool
            if sound.check(gamestate):
                is_warcry = any(instruction.type() == "warcry" for instruction in sound.instructions)
                if is_warcry: valid_warcry_horns.append(sound)
                else: valid_regular_horns.append(sound)

        def _play():
            warcry_song = None
            regular_horn_segment = None
            total_duration_ms = 0
            new_position_info = {}

            # Prepare audio segments and calculate total duration first
            if valid_warcry_horns:
                warcry_song = AudioSegment.from_file(valid_warcry_horns[0].songname)
                total_duration_ms += len(warcry_song)

            if valid_regular_horns:
                horn_info = valid_regular_horns[0]
                song_path = horn_info.songname
                last_position = self.goalhorn_positions.get(song_path, 0)
                
                full_song = AudioSegment.from_file(song_path)
                segment_to_play = full_song[last_position:]
                segment_to_play = segment_to_play[:45 * 1000]
                
                regular_horn_segment = segment_to_play
                total_duration_ms += len(regular_horn_segment)
                
                new_pos = last_position + len(segment_to_play)
                new_position_info = {
                    "path": song_path,
                    "position": 0 if new_pos >= len(full_song) else new_pos
                }

            # Make a single API call for the combined duration
            if total_duration_ms > 0:
                self._notify_bot_to_mute(total_duration_ms / 1000)

            # Now, play the prepared audio
            if warcry_song:
                logging.info(f"Playing warcry for team {team_name}: {valid_warcry_horns[0].songname}")
                self._play_audio(warcry_song)

            if regular_horn_segment:
                logging.info(f"Playing goal sound for scorer {scorer} of team {team_name}: {valid_regular_horns[0].songname}")
                self._play_audio(regular_horn_segment, fade_out_ms=5000)
                # Update position after playback
                self.goalhorn_positions[new_position_info["path"]] = new_position_info["position"]

            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play)
            self.playback_thread.start()

audio_manager = AudioManager()