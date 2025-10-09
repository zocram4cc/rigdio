from flask import Flask, request, jsonify
import threading
import time
from thefuzz import fuzz
from songgui import PlayerButtons
from chantswindow import ChantsButton

def start_webserver(rigdio_instance, port):
    app = Flask(__name__)

    def play_sound_with_duration(button, duration):
        if isinstance(button, PlayerButtons):
            button.playSong()
            if duration:
                time.sleep(duration)
                button.clists.pauseSong()
        elif isinstance(button, ChantsButton):
            button.playButton.invoke()
            if duration:
                time.sleep(duration)
                button.chantsManager.endThread()

    def play_anthem_sequence(duration=50):
        if not rigdio_instance.away or not rigdio_instance.home:
            print("Home and away teams must be loaded.")
            return

        # Play away anthem
        rigdio_instance.away.anthemButton.playSong()
        time.sleep(duration)
        rigdio_instance.away.anthemButton.clists.pauseSong()

        # Play home anthem
        rigdio_instance.home.anthemButton.playSong()
        time.sleep(duration)
        rigdio_instance.home.anthemButton.clists.pauseSong()

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

        try:
            rigdio_instance.legacyLoad(home_file, home=True)
            rigdio_instance.legacyLoad(away_file, home=False)
            return jsonify({"status": "success", "message": f"Loaded teams: {home_team} (home) and {away_team} (away)"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route('/api/chant', methods=['POST'])
    def play_chant():
        data = request.get_json()
        team = data.get('team') if data else None
        duration = data.get('duration', 15) if data else 15

        button = rigdio_instance.randomHome if team == rigdio_instance.game.home_name else rigdio_instance.randomAway
        thread = threading.Thread(target=play_sound_with_duration, args=(button, duration))
        thread.start()

        return jsonify({"status": "success", "message": f"Playing chant for {team or 'random team'}"})

    @app.route('/api/goal', methods=['POST'])
    def goal():
        data = request.get_json()
        team = data.get('team')
        scorer = data.get('scorer')
        duration = data.get('duration', 45) if data else 45

        if not team:
            return jsonify({"error": "'team' is a required field."}), 400

        team_menu = rigdio_instance.home if team.lower() == rigdio_instance.game.home_name.lower() else rigdio_instance.away
        if not team_menu:
            return jsonify({"error": f"Team '{team}' not loaded."}), 404

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

        thread = threading.Thread(target=play_sound_with_duration, args=(button_to_play, duration))
        thread.start()
        return jsonify({"status": "success", "message": message})


    @app.route('/api/victory', methods=['POST'])
    def victory():
        data = request.get_json()
        team = data.get('team')
        duration = data.get('duration', 90) if data else 90

        if not team:
            return jsonify({"error": "'team' is a required field."}), 400

        team_menu = rigdio_instance.home if team.lower() == rigdio_instance.game.home_name.lower() else rigdio_instance.away
        if not team_menu:
            return jsonify({"error": f"Team '{team}' not loaded."}), 404

        thread = threading.Thread(target=play_sound_with_duration, args=(team_menu.victoryButton, duration))
        thread.start()
        return jsonify({"status": "success", "message": f"Playing victory anthem for {team}."})

    @app.route('/api/anthems', methods=['POST'])
    def anthems():
        data = request.get_json()
        duration = data.get('duration', 50) if data else 50

        thread = threading.Thread(target=play_anthem_sequence, args=(duration,))
        thread.start()

        return jsonify({"status": "success", "message": "Anthem sequence started."})

    def run_app():
        app.run(port=port)

    thread = threading.Thread(target=run_app)
    thread.daemon = True
    thread.start()