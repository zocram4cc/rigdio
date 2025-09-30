import threading
import time
import random
import logging
from pydub import AudioSegment
from pydub.playback import play

class AudioManager:
    def __init__(self):
        self.home_team = None
        self.away_team = None
        self.home_music = {}
        self.away_music = {}
        self.playback_thread = None

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

        away_anthem = self.away_music.get("anthem")
        home_anthem = self.home_music.get("anthem")

        if not away_anthem or not home_anthem:
            logging.warning("Anthem files not found, skipping playback")
            return

        def _play_sequence():
            # Play away anthem
            logging.info(f"Playing away anthem: {away_anthem[0].songname}")
            away_song = AudioSegment.from_file(away_anthem[0].songname)
            self._play_audio(away_song, 70 * 1000, 5 * 1000)

            # Play home anthem
            logging.info(f"Playing home anthem: {home_anthem[0].songname}")
            home_song = AudioSegment.from_file(home_anthem[0].songname)
            self._play_audio(home_song, 70 * 1000, 5 * 1000)

            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play_sequence)
            self.playback_thread.start()

    def load_team_music(self, team_id, is_home):
        # Logic to load music for a team will go here
        pass

    def play_victory_anthem(self, team):
        if team == "home":
            music_dict = self.home_music
            team_name = self.home_team
        elif team == "away":
            music_dict = self.away_music
            team_name = self.away_team
        else:
            logging.error(f"Invalid team specified for victory anthem: {team}")
            return

        victory_anthem = music_dict.get("victory")
        if not victory_anthem:
            logging.warning(f"No victory anthem found for team {team_name}")
            return

        def _play():
            logging.info(f"Playing victory anthem for team {team_name}: {victory_anthem[0].songname}")
            song = AudioSegment.from_file(victory_anthem[0].songname)
            self._play_audio(song, 90 * 1000, 5 * 1000)
            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play)
            self.playback_thread.start()

    def play_warcry(self):
        team_choice = random.choice(["home", "away"])
        music_dict = self.home_music if team_choice == "home" else self.away_music
        team_name = self.home_team if team_choice == "home" else self.away_team

        chants = music_dict.get("chant")
        if not chants:
            logging.warning(f"No chants found for team {team_name}")
            return

        chant_to_play = random.choice(chants)

        def _play():
            logging.info(f"Playing warcry for team {team_name}: {chant_to_play.songname}")
            song = AudioSegment.from_file(chant_to_play.songname)
            self._play_audio(song)
            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play)
            self.playback_thread.start()

    def play_goal_sound(self, team, scorer):
        if team == "home":
            music_dict = self.home_music
            team_name = self.home_team
        elif team == "away":
            music_dict = self.away_music
            team_name = self.away_team
        else:
            logging.error(f"Invalid team specified for goal sound: {team}")
            return

        # Attempt to find a case-insensitive match for the scorer
        goal_sound = None
        scorer_lower = scorer.lower()
        for key, value in music_dict.items():
            if key.lower() == scorer_lower:
                goal_sound = value
                break

        if not goal_sound:
            logging.info(f"No specific goal sound for scorer {scorer}, falling back to generic goal horn for team {team_name}")
            # Attempt to find a case-insensitive match for the generic "goal" sound
            for key, value in music_dict.items():
                if key.lower() == "goal":
                    goal_sound = value
                    break

        if not goal_sound:
            logging.warning(f"No generic goal horn found for team {team_name}")
            return

        def _play():
            logging.info(f"Playing goal sound for scorer {scorer} of team {team_name}: {goal_sound[0].songname}")
            song = AudioSegment.from_file(goal_sound[0].songname)
            song = song[:45 * 1000] # Cut off after 45 seconds
            self._play_audio(song)
            self.playback_thread = None

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.playback_thread = threading.Thread(target=_play)
            self.playback_thread.start()

audio_manager = AudioManager()
