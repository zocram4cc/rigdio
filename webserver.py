from flask import Flask, request, jsonify
import threading
import time
import requests
import logging
import json
import os
import random
from thefuzz import fuzz
from songgui import PlayerButtons
from chantswindow import ChantsButton
from event import EventManager

bot_api_url = "http://localhost:31335/api/mute"

def _notify_bot_to_mute(duration_seconds):
    if duration_seconds <= 0: return
    payload = {"duration": int(duration_seconds + 2)}
    headers = {"Content-Type": "application/json"}
    logging.info(f"Requesting bot mute for {payload['duration']} seconds.")
    try:
        response = requests.post(bot_api_url, data=json.dumps(payload), headers=headers, timeout=1)
        if response.status_code != 200:
            logging.warning(f"API call to mute bot failed with status {response.status_code}: {response.text}")
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not connect to the bot API to request mute. Is it running? Error: {e}")

def start_webserver(rigdio_instance, port):
    app = Flask(__name__)
    playback_lock = threading.Lock()
    playback_interrupt_event = threading.Event()

    def play_sound_with_duration(button, duration):
        if duration:
            _notify_bot_to_mute(duration)
        if isinstance(button, PlayerButtons):
            button.playSong()
            if duration:
                playback_interrupt_event.wait(timeout=duration)
                playback_interrupt_event.clear()
                button.clists.pauseSong()
        elif isinstance(button, ChantsButton):
            button.playButton.invoke()
            if duration:
                playback_interrupt_event.wait(timeout=duration)
                playback_interrupt_event.clear()
                button.chantsManager.endThread()

    def play_anthem_sequence(duration=50):
        if not rigdio_instance.away or not rigdio_instance.home:
            print("Home and away teams must be loaded.")
            return

        # Play away anthem
        duration_both_anthems=duration*2
        _notify_bot_to_mute(duration_both_anthems)
        rigdio_instance.away.anthemButton.playSong()
        if playback_interrupt_event.wait(timeout=duration):
            rigdio_instance.away.anthemButton.clists.pauseSong()
            playback_interrupt_event.clear()
            return # interrupted
        rigdio_instance.away.anthemButton.clists.pauseSong()

        # Play home anthem
        #_notify_bot_to_mute(duration)
        rigdio_instance.home.anthemButton.playSong()
        if playback_interrupt_event.wait(timeout=duration):
            rigdio_instance.home.anthemButton.clists.pauseSong()
            playback_interrupt_event.clear()
            return # interrupted
        rigdio_instance.home.anthemButton.clists.pauseSong()

    def team_menu_for(data):
        """The loaded team a request names: 'side' (home/away) wins over 'team' (a team name)."""
        side = (data.get('side') or '').lower()
        if side in ('home', 'away'):
            return getattr(rigdio_instance, side)
        home_name = rigdio_instance.game.home_name or ''
        return rigdio_instance.home if data.get('team', '').lower() == home_name.lower() else rigdio_instance.away

    @app.route('/api/load', methods=['POST'])
    def load_teams():
        data = request.get_json()
        home_team = data.get('home')
        away_team = data.get('away')

        if not home_team or not away_team:
            return jsonify({"error": "Both 'home' and 'away' teams are required."}), 400

        # Construct file paths
        home_file = f"music/{home_team}/{home_team}.4ccm"
        away_file = f"music/{away_team}/{away_team}.4ccm"

        # same teams again (e.g. a reconnect) must not reset the score
        if rigdio_instance.home and rigdio_instance.away and \
           (rigdio_instance.game.home_name, rigdio_instance.game.away_name) == (home_team.lower(), away_team.lower()):
            return jsonify({"status": "success", "message": "Teams already loaded."})
        missing = [f for f in (home_file, away_file) if not os.path.isfile(f)]
        if missing:
            return jsonify({"error": f"No export at {', '.join(missing)}."}), 404

        try:
            rigdio_instance.legacyLoad(home_file, home=True)
            rigdio_instance.legacyLoad(away_file, home=False)
            return jsonify({"status": "success", "message": f"Loaded teams: {home_team} (home) and {away_team} (away)"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/chant', methods=['POST'])
    def play_chant():
        if not playback_lock.acquire(blocking=False):
            return jsonify({"error": "A sound is already playing."}), 409

        data = request.get_json(silent=True) or {}
        team = data.get('team')
        duration = data.get('duration', 15)
        side = (data.get('side') or '').lower()
        if side not in ('home', 'away'):
            side = ('home' if team == rigdio_instance.game.home_name else 'away') if team else random.choice(['home', 'away'])
        button = rigdio_instance.randomHome if side == 'home' else rigdio_instance.randomAway
        
        def target_with_lock(button, duration):
            try:
                play_sound_with_duration(button, duration)
            finally:
                playback_lock.release()

        thread = threading.Thread(target=target_with_lock, args=(button, duration))
        thread.start()

        return jsonify({"status": "success", "message": f"Playing chant for {side}"})

    @app.route('/api/goal', methods=['POST'])
    def goal():
        data = request.get_json(silent=True) or {}
        team = data.get('team') or data.get('side')
        scorer = data.get('scorer')
        duration = data.get('duration', 45)

        if not team:
            return jsonify({"error": "'team' or 'side' is required."}), 400
        team_menu = team_menu_for(data)
        if not team_menu:
            return jsonify({"error": f"Team '{team}' not loaded."}), 404

        if playback_lock.locked():
            playback_interrupt_event.set()

        lock_acquired = playback_lock.acquire(timeout=2)

        if not lock_acquired:
            return jsonify({"error": "Could not acquire playback lock, another sound is playing."}), 409

        button_to_play = team_menu.goalButton
        message = "Playing standard goalhorn."

        if scorer:
            best_match = None
            highest_ratio = 0
            for button in team_menu.buttons:
                # only check goalscorer buttons
                if not button.reserved:
                    ratio = fuzz.partial_ratio(scorer.lower(), button.pname.lower())
                    if ratio > highest_ratio:
                        highest_ratio = ratio
                        best_match = button
            
            if highest_ratio > 70: # Threshold for a good match
                button_to_play = best_match
                message = f"Goal for {scorer}!"
            else:
                message = f"No specific horn for {scorer}, playing standard goalhorn."

        def target_with_lock(button, duration):
            try:
                play_sound_with_duration(button, duration)
            finally:
                playback_lock.release()

        thread = threading.Thread(target=target_with_lock, args=(button_to_play, duration))
        thread.start()
        return jsonify({"status": "success", "message": message})


    @app.route('/api/victory', methods=['POST'])
    def victory():
        data = request.get_json(silent=True) or {}
        team = data.get('team') or data.get('side')
        duration = data.get('duration', 90)

        if not team:
            return jsonify({"error": "'team' or 'side' is required."}), 400

        team_menu = team_menu_for(data)
        if not team_menu:
            return jsonify({"error": f"Team '{team}' not loaded."}), 404

        if not playback_lock.acquire(blocking=False):
            return jsonify({"error": "A sound is already playing."}), 409

        def target_with_lock(button, duration):
            try:
                play_sound_with_duration(button, duration)
            finally:
                playback_lock.release()

        thread = threading.Thread(target=target_with_lock, args=(team_menu.victoryButton, duration))
        thread.start()
        return jsonify({"status": "success", "message": f"Playing victory anthem for {team}."})

    @app.route('/api/event', methods=['POST'])
    def match_event():
        """A player's sub/card/own-goal clip (.4ccm 'event' instruction)."""
        data = request.get_json(silent=True) or {}
        etype, player = data.get('event'), data.get('player')
        if etype not in EventManager.types or not player:
            return jsonify({"error": f"'event' must be one of {EventManager.types}; 'player' is required."}), 400
        # either team may own the clip, as with the old SENPAI listener
        for manager in (rigdio_instance.events.home, rigdio_instance.events.away):
            manager.checkAndPlay(player.upper(), etype, int(data.get('minute', 0)))
        return jsonify({"status": "success", "message": f"{etype} for {player}."})

    @app.route('/api/anthems', methods=['POST'])
    def anthems():
        if not rigdio_instance.away or not rigdio_instance.home:
            return jsonify({"error": "Home and away teams must be loaded."}), 400

        if not playback_lock.acquire(blocking=False):
            return jsonify({"error": "A sound is already playing."}), 409

        data = request.get_json()
        duration = data.get('duration', 50) if data else 50

        def target_with_lock(duration):
            try:
                play_anthem_sequence(duration)
            finally:
                playback_lock.release()

        thread = threading.Thread(target=target_with_lock, args=(duration,))
        thread.start()

        return jsonify({"status": "success", "message": "Anthem sequence started."})

    def run_app():
        app.run(port=port)

    thread = threading.Thread(target=run_app)
    thread.daemon = True
    thread.start()
