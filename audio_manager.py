import threading
import time
import random
import logging
import requests
import json
import vlc
import os
from thefuzz import process
from rigdio_except import UnloadSong
from condition import GoalCondition, FirstCondition, NotCondition, WarcryInstruction

class AudioManager:
    def __init__(self):
        self.home_team = None
        self.away_team = None
        self.home_music = {}
        self.away_music = {}
        self.playback_thread = None
        self.goalhorn_positions = {}
        self.bot_api_url = "http://localhost:31335/api/mute"
        self.goal_counters = {}
        # A single, persistent VLC instance and player for stability and control.
        self.vlc_instance = vlc.Instance("--no-video --audio-filter=aout_fade")
        self.player = self.vlc_instance.media_player_new()
        self.stop_event = threading.Event()

    def clear_goalhorn_positions(self):
        self.goalhorn_positions.clear()
        self.goal_counters.clear()

    def _find_fuzzy_scorer_match(self, scorer, music_dict, threshold=80):
        """
        Finds the best fuzzy match for a scorer's name in the music dictionary.
        """
        # Get a list of all potential scorer names (excluding generic keys like 'goal')
        scorer_keys = [key for key in music_dict.keys() if key != "goal"]
        if not scorer_keys:
            return []

        # Use thefuzz to find the single best match from the list of keys
        best_match, score = process.extractOne(scorer, scorer_keys)

        # Check if the score meets our confidence threshold
        if score >= threshold:
            logging.info(f"Fuzzy match found for '{scorer}': '{best_match}' (Score: {score})")
            return music_dict.get(best_match, [])
        else:
            logging.info(f"No fuzzy match for '{scorer}'. Best attempt '{best_match}' had score {score} (Threshold: {threshold})")
            return []

    def _notify_bot_to_mute(self, duration_seconds):
        if duration_seconds <= 0: return
        payload = {"duration": int(duration_seconds + 2)}
        headers = {"Content-Type": "application/json"}
        logging.info(f"Requesting bot mute for {payload['duration']} seconds.")
        try:
            response = requests.post(self.bot_api_url, data=json.dumps(payload), headers=headers, timeout=1)
            if response.status_code != 200:
                logging.warning(f"API call to mute bot failed with status {response.status_code}: {response.text}")
        except requests.exceptions.RequestException as e:
            logging.warning(f"Could not connect to the bot API to request mute. Is it running? Error: {e}")

    def stop_playback(self):
        """Instantly stops any currently playing audio."""
        if self.player.is_playing():
            logging.info("Stopping VLC playback.")
            self.player.stop()
        # Signal any waiting thread to terminate
        self.stop_event.set()
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join()
        self.stop_event.clear()

    def _play_audio(self, file_path, start_ms=0, duration_ms=None):
        """Plays an audio file using VLC, waiting for it to end via events."""
        if self.stop_event.is_set(): return

        # Use a local threading.Event to signal completion from the callback.
        playback_finished = threading.Event()

        def end_callback(event):
            """Called by VLC when the media ends."""
            logging.debug(f"VLC end event triggered for {file_path}")
            playback_finished.set()

        media = self.vlc_instance.media_new(file_path)
        
        # Attach event listener
        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached, end_callback)

        # Use VLC options to handle slicing
        options = []
        if start_ms > 0:
            options.append(f"start-time={start_ms / 1000.0}")
        if duration_ms:
            options.append(f"stop-time={(start_ms + duration_ms) / 1000.0}")
        
        if options:
            media.add_options(*options)
        
        self.player.set_media(media)
        media.release()

        logging.info(f"Playing '{file_path}' with options: {options}")
        self.player.play()
        
        # Wait for the event to be set, or for a global stop signal.
        while not playback_finished.is_set():
            if self.stop_event.is_set():
                self.player.stop()
                break
            time.sleep(0.05) # Short sleep to avoid busy-waiting

        # Cleanup: detach the event listener to avoid it being called for subsequent plays.
        events.event_detach(vlc.EventType.MediaPlayerEndReached)
        logging.debug(f"Finished waiting for {file_path}")

    def _select_anthem(self, anthem_candidates, gametype, opponent_name):
        """
        Selects the most specific valid anthem by first validating candidates
        and then scoring the ones that pass.
        """
        best_match = None
        highest_score = -1

        for anthem in anthem_candidates:
            is_valid = True
            current_score = 0
            
            conditions = getattr(anthem, 'conditions', [])

            # 1. VALIDATION: Disqualify the anthem if any condition explicitly conflicts.
            for condition in conditions:
                cond_type = getattr(condition, 'type', lambda: None)()

                # A 'match' condition only disqualifies if a gametype exists AND it doesn't match.
                if cond_type == 'match' and gametype and not condition.check_match_type(gametype):
                    is_valid = False
                    break

                # An 'opponent' condition requires an opponent to be present and match.
                if cond_type == 'opponent':
                    required_opponents = [t.lower() for t in getattr(condition, 'tokens', lambda: [])()]
                    if not opponent_name or opponent_name.lower() not in required_opponents:
                        is_valid = False
                        break
            
            if not is_valid:
                continue # This anthem is disqualified, move to the next one.

            # 2. SCORING: If the anthem is valid, score it based on what it matches.
            for condition in conditions:
                cond_type = getattr(condition, 'type', lambda: None)()
                
                # Check for an opponent match
                if cond_type == 'opponent':
                    required_opponents = [t.lower() for t in getattr(condition, 'tokens', lambda: [])()]
                    if opponent_name and opponent_name.lower() in required_opponents:
                        current_score += 2 # Opponent match is high priority

                # Check for a gametype match
                if cond_type == 'match':
                    if gametype and condition.check_match_type(gametype):
                        current_score += 1 # Gametype match is lower priority

            # 3. SELECTION: If this is the best valid anthem so far, choose it.
            if current_score >= highest_score:
                highest_score = current_score
                best_match = anthem
        
        if best_match:
            logging.info(f"Selected anthem: {best_match.songname} (Score: {highest_score}) for opponent '{opponent_name}' and gametype '{gametype}'")
        else:
            # This warning should now only appear if there's truly no default
            logging.warning(f"No suitable anthem found for opponent '{opponent_name}' and gametype '{gametype}'.")
            
        return best_match

    def _start_playback_thread(self, target_func, args_tuple=()):
        """Helper to safely stop any existing thread before starting a new one."""
        self.stop_playback()
        self.playback_thread = threading.Thread(target=target_func, args=args_tuple)
        self.playback_thread.start()

    def play_anthems(self, gamestate):
        home_anthem_candidates = self.home_music.get("anthem", [])
        away_anthem_candidates = self.away_music.get("anthem", [])
        home_anthem = self._select_anthem(home_anthem_candidates, gamestate.gametype, self.away_team)
        away_anthem = self._select_anthem(away_anthem_candidates, gamestate.gametype, self.home_team)
        if home_anthem is None or away_anthem is None:
            logging.warning("Could not select one or both anthems, skipping playback.")
            return

        def _play_sequence():
            self._notify_bot_to_mute(duration_seconds=140)
            self._play_audio(away_anthem.songname, duration_ms=70000)
            self._play_audio(home_anthem.songname, duration_ms=70000)
        
        self._start_playback_thread(_play_sequence)

    def load_team_music(self, team_id, is_home):
        pass

    def play_victory_anthem(self, team):
        music_dict = self.home_music if team == "home" else self.away_music
        victory_anthem = music_dict.get("victory")
        if not victory_anthem:
            logging.warning(f"No victory anthem found for team {'home' if team == 'home' else 'away'}")
            return
        
        anthem_path = victory_anthem[0].songname
        def _play():
            self._notify_bot_to_mute(duration_seconds=90)
            self._play_audio(anthem_path, duration_ms=90000)
            
        self._start_playback_thread(_play)

    def play_warcry(self):
        music_dict = self.home_music if random.choice(["home", "away"]) == "home" else self.away_music
        chants = music_dict.get("chant")
        if not chants:
            logging.warning(f"No chants found for team {'home' if music_dict is self.home_music else 'away'}")
            return
            
        chant_path = random.choice(chants).songname
        def _play():
            # We can't get duration without pydub, so using a fixed mute time
            self._notify_bot_to_mute(duration_seconds=30)
            self._play_audio(chant_path)

        self._start_playback_thread(_play)

    def _conditions_are_met(self, condition_objects, gamestate):
        if not condition_objects:
            return True

        for condition in condition_objects:
            # Override for 'not first' to use scorer_goals, which is what the user expects in this context.
            if isinstance(condition, NotCondition) and \
               len(condition.subconditions()) == 1 and \
               isinstance(condition.subconditions()[0], FirstCondition):
                
                if gamestate.scorer_goals == 1:
                    return False  # It IS the scorer's first goal, so 'not first' is False.
                else:
                    continue  # This condition passes, check the next one.

            # Override for 'goals' to use scorer_goals, but NOT for its subclasses
            if type(condition) is GoalCondition:
                try:
                    op = condition.tokens()[0]
                    val = int(condition.tokens()[1])
                    actual = gamestate.scorer_goals
                    
                    if op == '==' and not (actual == val): return False
                    elif op == '>=' and not (actual >= val): return False
                    elif op == '<=' and not (actual <= val): return False
                    elif op == '>' and not (actual > val): return False
                    elif op == '<' and not (actual < val): return False
                    elif op == '!=' and not (actual != val): return False
                except (ValueError, IndexError) as e:
                    logging.warning(f"Could not evaluate GoalCondition with tokens {condition.tokens()}: {e}")
                    return False
                
                continue # This condition passed, continue to the next one.

            # For any other type of condition, use its default check method.
            # This is important for conditions like 'opponent', 'match', etc.
            try:
                if not condition.check(gamestate):
                    return False
            except UnloadSong:
                # This song is marked to be unloaded, so treat its conditions as not met.
                return False
            except Exception as e:
                logging.warning(f"An unexpected error occurred while checking condition {condition}: {e}")
                return False
        
        # If we looped through all conditions and none of them failed, the sound is valid.
        return True


    def play_goal_sound(self, team, scorer, gamestate):
        self.stop_playback()
        music_dict = self.home_music if team == "home" else self.away_music
        
        # 1. Increment goal count
        scorer_key = scorer.lower()
        current_goals = self.goal_counters.get(scorer_key, 0) + 1
        self.goal_counters[scorer_key] = current_goals
        gamestate.scorer_goals = current_goals
        logging.info(f"'{scorer}' has now scored {current_goals} goal(s).")

        # 2. Find all possible sounds
        scorer_sounds = self._find_fuzzy_scorer_match(scorer, music_dict)
        all_possible_sounds = scorer_sounds + music_dict.get("goal", [])
        
        if not all_possible_sounds: return

        # 3. Find and separate all possible sounds into categories
        warcries = []
        scorer_specific_regulars = []
        generic_regulars = []

        for sound in all_possible_sounds:
            is_warcry_tag = any(hasattr(inst, 'type') and inst.type() == 'warcry' for inst in getattr(sound, 'instructions', []))
            is_generic_goal = getattr(sound, 'pname', '').lower() == 'goal'

            if is_warcry_tag:
                warcries.append(sound)
            elif not is_generic_goal:
                scorer_specific_regulars.append(sound)
            else:
                generic_regulars.append(sound)

        # 4. Select the horns to play, checking conditions with priority
        warcry_to_play = None
        for cry in warcries:
            if self._conditions_are_met(getattr(cry, 'conditions', []), gamestate):
                warcry_to_play = cry
                break  # Use the first valid warcry

        regular_to_play = None
        # First, try to find a valid scorer-specific regular horn
        for sound in scorer_specific_regulars:
            if self._conditions_are_met(getattr(sound, 'conditions', []), gamestate):
                regular_to_play = sound
                break  # Use the first valid scorer-specific horn

        # If no valid scorer-specific horn was found, fall back to a generic horn
        if not regular_to_play:
            for sound in generic_regulars:
                if self._conditions_are_met(getattr(sound, 'conditions', []), gamestate):
                    regular_to_play = sound
                    break  # Use the first valid generic horn
    

        # 5. Play the sequence
        def _play(warcry_horn, regular_to_play):
            logging.debug("Playback thread started.")
            self._notify_bot_to_mute(duration_seconds=60)
            if warcry_horn:
                self._play_audio(warcry_horn.songname)
            print(f"{self.goalhorn_positions}")
            start_ms = self.goalhorn_positions.get(regular_to_play.songname, 0)
            print(f"{start_ms}")
            self._play_audio(regular_to_play.songname, start_ms=start_ms, duration_ms=45000)
            new_pos = start_ms + 45000
            self.goalhorn_positions[regular_to_play.songname] = new_pos

        #     logging.debug("Warcry playback finished. Checking for regular horn.")
        #     # After the warcry finishes (or if there was no warcry), play the regular horn.
        #     if self.stop_event.is_set():
        #         logging.error("STOP_EVENT IS SET. Aborting regular horn playback.")
        #         return
            
        #     if regular_to_play:
        #         logging.debug(f"Regular horn path is present: {regular_to_play.songname}")
        #         song_path = regular_to_play
        #         start_ms = self.goalhorn_positions.get(song_path, 0)
        #         logging.info(f"--- Playing REGULAR HORN for {scorer}: {song_path} ---")
        #         self._play_audio(song_path, start_ms=start_ms, duration_ms=45000)
        #         new_pos = start_ms + 45000
        #         self.goalhorn_positions[song_path] = new_pos
        #     else:
        #         logging.warning("regular_horn_path is None. Cannot play regular horn.")
        #     logging.debug("Playback thread finished.")
        # print(f"-- {regular_to_play.songname}")

        self._start_playback_thread(_play, args_tuple=(warcry_to_play, regular_to_play))
audio_manager = AudioManager()