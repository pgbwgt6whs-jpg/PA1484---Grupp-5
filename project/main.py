import sys
import time
import lvgl as lv
import network
import urequests 

from board_lvgl import start_board
from debug_log import log


from secrets import WIFI_SSID, WIFI_PASSWORD, TRAFIKLAB_API_KEY

API_BASE = "https://realtime-api.trafiklab.se/v1"
# These are name-search paths, not stop IDs. The stop IDs come from Stop Lookup.
# Stop IDs from Trafiklab Stop Lookup
STOP_IDS = {
    "Karlskrona Centralstation": "740000230",
    "Campus Gräsvik": "740032188"
}
TRANSPORT_MODES = {"Bus": "BUS", "Train": "TRAIN", "Ferry": "BOAT", "All": None}


class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()
        self.tile2_dark = False
        self.transport_type = "All" # Stores the currently selected transportation type, where "All" is used as the default value.
        self.selected_stop = "Karlskrona Centralstation"  # Stores the currently selected stop, with Karlskrona Centralstation as the default value.

        self.load_settings()

        self.create_ui()
        self.connect_wifi()
        self.update_departure_screen()
        log("student application ready")

    @staticmethod
    def apply_tile_colors(tile, label, dark):
        tile.set_style_bg_opa(lv.OPA.COVER, 0)
        tile.set_style_bg_color(
            lv.color_hex(0x000000 if dark else 0xFFFFFF), 0
        )
        label.set_style_text_color(
            lv.color_hex(0xFFFFFF if dark else 0x000000), 0
        )

    def on_tile2_clicked(self, _event):
        self.tile2_dark = not self.tile2_dark
        self.style_departure_screen()

    def style_departure_screen(self):
            #Apply the selected color theme to the departure board
            dark = self.tile2_dark
            bg = 0x0B1324 if dark else 0xF3F6FC
            card_bg = 0x1B2B43 if dark else 0xFFFFFF
            fg = 0xFFFFFF if dark else 0x152338
            muted = 0xB7C7DA if dark else 0x53657A
    
            self.tile2.set_style_bg_opa(lv.OPA.COVER, 0)
            self.tile2.set_style_bg_color(lv.color_hex(bg), 0)
            self.departure_title.set_style_text_color(lv.color_hex(fg), 0)
            self.departure_stop_label.set_style_text_color(lv.color_hex(muted), 0)
            self.departure_info_label.set_style_text_color(lv.color_hex(muted), 0)
            for label in self.departure_headers:
                label.set_style_text_color(lv.color_hex(muted), 0)
            for row in self.departure_rows:
                row["panel"].set_style_bg_color(lv.color_hex(card_bg), 0)
                for column in ("time", "line", "destination"):
                    row[column].set_style_text_color(lv.color_hex(fg), 0)
                # A status is easier to scan with a separate color.
                status_text = row["status_text"]
                if status_text.startswith("Delayed"):
                    status_color = 0xF9BF65 if dark else 0xA76411
                elif status_text == "Cancelled":
                    status_color = 0xFF8C94 if dark else 0xB42332
                elif status_text == "On time":
                    status_color = 0x60E0B5 if dark else 0x117D57
                else:
                    status_color = muted
                row["status"].set_style_text_color(lv.color_hex(status_color), 0)

    def create_ui(self):
        'Function: Creates UI'
        self.tileview = lv.tileview(lv.screen_active())
        self.tileview.set_size(600, 450)
        self.tileview.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)

        # Creates the three main screens as tiles
        self.tile1 = self.tileview.add_tile(0, 0, lv.DIR.RIGHT) # Tile 1 can be swiped to the right.
        self.tile2 = self.tileview.add_tile(1, 0, lv.DIR.LEFT | lv.DIR.RIGHT) # Tile 2 is located between tile 1 och tile 3, so navigation is allowed in both directions.
        self.tile3 = self.tileview.add_tile(2, 0, lv.DIR.LEFT) # Tile 3 is the settings screen, so it can be swiped back to tile 2.

        self.tile1_label = lv.label(self.tile1)
        Intro_text = (
            "Public Transportation Information\n"
            "Version 1.0\n"
            "Grupp 5\n"
            "Members: Mette, Emily, \nSedra, Elsa & Ayat"
            "\nAll data is provided\nby TrafikLab"
        )
        self.tile1_label.set_text(Intro_text)
        self.tile1_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile1_label.center()
        self.apply_tile_colors(self.tile1, self.tile1_label, False)
        
        
    #-----------------------------------------------
    #Creating departure screen - FR2
    #-----------------------------------------------
        self.departure_title = lv.label(self.tile2)
        self.departure_title.set_text("DEPARTURES")
        self.departure_title.set_style_text_font(lv.font_montserrat_28, 0)
        self.departure_title.align(lv.ALIGN.TOP_LEFT, 18, 12)
        self.tile2_label = self.departure_title  # Compatibility with older UI code.

        self.departure_stop_label = lv.label(self.tile2)
        self.departure_stop_label.set_width(560)
        self.departure_stop_label.set_text(self.selected_stop)
        self.departure_stop_label.align(lv.ALIGN.TOP_LEFT, 20, 62)

        self.departure_headers = []
        for name, x in (("TIME", 28), ("LINE", 115),
                        ("DESTINATION", 200), ("STATUS", 434)):
            header = lv.label(self.tile2)
            header.set_text(name)
            header.align(lv.ALIGN.TOP_LEFT, x, 101)
            self.departure_headers.append(header)

        # Fixed positions mean the columns line up with any font.
        self.departure_rows = []
        for index in range(6):
            panel = lv.obj(self.tile2)
            panel.set_size(568, 42)
            panel.align(lv.ALIGN.TOP_LEFT, 16, 127 + index * 46)
            panel.set_style_bg_opa(lv.OPA.COVER, 0)
            panel.set_style_radius(8, 0)
            panel.set_style_border_width(0, 0)
            panel.remove_flag(lv.obj.FLAG.SCROLLABLE)
            panel.remove_flag(lv.obj.FLAG.CLICKABLE)

            row = {"panel": panel, "status_text": ""}
            for column, x in (("time", 10), ("line", 98),
                              ("destination", 182), ("status", 417)):
                label = lv.label(panel)
                label.set_text("")
                label.align(lv.ALIGN.TOP_LEFT, x, 11)
                row[column] = label
            self.departure_rows.append(row)

        self.departure_info_label = lv.label(self.tile2)
        self.departure_info_label.set_width(560)
        self.departure_info_label.set_text("Waiting for Trafiklab...")
        self.departure_info_label.align(lv.ALIGN.TOP_LEFT, 20, 413)

        self.style_departure_screen()
        self.tile2.add_flag(lv.obj.FLAG.CLICKABLE)
        self.tile2.add_event_cb(self.on_tile2_clicked, lv.EVENT.CLICKED, None)

        # -----------------------------------------------
        # Settings Screen - FR6
        # -----------------------------------------------
        # Creates the title for the settings screen. 
        self.settings_title = lv.label(self.tile3)
        self.settings_title.set_text("Settings")
        self.settings_title.set_style_text_font(lv.font_montserrat_28, 0) # Sets the front size of the settings title.
        self.settings_title.align(lv.ALIGN.TOP_MID, 0, 30) # Positions the title at the top center of the screen.

        # Creates a label for the traffic data display settings (settings related to how traffic data is displayed can be placed below).
        self.traffic_settings_label = lv.label(self.tile3)
        self.traffic_settings_label.set_text("Traffic data display")
        self.traffic_settings_label.align(lv.ALIGN.TOP_LEFT, 50, 100) # Positions the section label below the Settings title.

        # -----------------------------------------------
        # Stop selection - FR7
        # -----------------------------------------------
        # Creates a label for the stop selection.
        self.stop_label = lv.label(self.tile3)
        self.stop_label.set_text("Select stop")
        self.stop_label.align(lv.ALIGN.TOP_LEFT, 50, 220)  # Positions the stop selection label on the settings screen.

        # Creates a dropdown menu for selecting a stop.
        self.stop_dropdown = lv.dropdown(self.tile3)    
        self.stop_dropdown.set_options("Karlskrona Centralstation\n" "Campus Gräsvik")  # Adds the available stops to the dropdown menu.   

        # Selects the previously saved stop instead of always selecting Karlskrona Centralstation
        stops = ["Karlskrona Centralstation", "Campus Gräsvik"] 
        if self.selected_stop in stops:
            self.stop_dropdown.set_selected(stops.index(self.selected_stop))
        else:
            self.stop_dropdown.set_selected(0) # Selects "Karlskrona Centralstation" as the default stop (dropdown indexes start at 0).
  
        self.stop_dropdown.set_width(250)  # Sets the width of the stop dropdown menu.
        self.stop_dropdown.align(lv.ALIGN.TOP_LEFT, 250, 210)  # Positions the stop dropdown next to the "Select stop" label.

        self.stop_dropdown.add_event_cb(
            self.on_stop_changed,
            lv.EVENT.VALUE_CHANGED,
            None
            )  # Calls on_stop_changed() when the user selects a different stop.


        # -----------------------------------------------
        # Transportation type selection - FR8
        # -----------------------------------------------
        # Creates a label describing the transportation type dropdown.
        self.transport_label = lv.label(self.tile3)
        self.transport_label.set_text("Transport type")
        self.transport_label.align(lv.ALIGN.TOP_LEFT, 50, 150) # Positions the label on the settings screen.

        # Dropdown menu implementation
        self.transport_dropdown = lv.dropdown(self.tile3) # Creates a dropdown menu on the settings screen.
        self.transport_dropdown.set_options("Bus\nTrain\nFerry\nAll") # Adds the four transportation types required by FR8.
        # FR9
        transport_options = ["Bus", "Train", "Ferry", "All"]

        if self.transport_type in transport_options:
            self.transport_dropdown.set_selected(transport_options.index(self.transport_type)) # Selects the previously saved transportation type instead of always selecting "All"
        else:
            self.transport_dropdown.set_selected(3) # Selects "All" as the default option (dropdown indexes start at 0).

        self.transport_dropdown.set_width(200) # Sets the width of the dropdown menu.
        self.transport_dropdown.align(lv.ALIGN.TOP_LEFT, 250, 140) # Positions the dropdown next to the "Transport type" label.
        self.transport_dropdown.add_event_cb(self.on_transport_changed,lv.EVENT.VALUE_CHANGED, None) # Calls on_transport_changed() whenever the user selects a different transportation type.

        # FR9: Save settings button
        self.save_button = lv.button(self.tile3)
        self.save_button.set_size(200, 45)
        self.save_button.align(lv.ALIGN.TOP_MID, 0, 290)
        # Create text inside the save button
        self.save_button_label = lv.label(self.save_button)
        self.save_button_label.set_text("Save as default")
        self.save_button_label.center()

        self.save_button.add_event_cb(self.save_settings, lv.EVENT.CLICKED, None) # Calls save_settings() when user clicks the button
        self.save_status_label = lv.label(self.tile3) # Creates label to display confirmation message
        self.save_status_label.set_text("")
        self.save_status_label.align(lv.ALIGN.TOP_MID, 0, 350)

       
    def on_stop_changed(self, event):
        """Updates the selected stop."""
        dropdown = event.get_target() # Gets the dropdown object that triggered the event.
        self.selected_stop = dropdown.get_selected_str() # Gets and stores the selected stop.
        log("Selected stop: " + self.selected_stop) # Prints the selected stop to the log for testing

    #---------------------------------------------------------------------
    #FR2 -Departure screen displaying live public transport departure data 
    #---------------------------------------------------------------------
    #API and departure handling functions
    @staticmethod
    def fetch_json(url):
        response = None
        try:
            response = urequests.get(url)
            if response.status_code != 200:
                raise RuntimeError("Trafiklab HTTP %s" % response.status_code)
            return response.json()
        finally:
            if response is not None:
                response.close()

    def get_stop_id(self):
        # Returns the ID of the selected stop
        return STOP_IDS[self.selected_stop]


    def get_departures(self):
        if not network.WLAN(network.STA_IF).isconnected():
            raise RuntimeError("Wi-Fi is disconnected")
        stop_id = self.get_stop_id()
        url = API_BASE + "/departures/" + stop_id + "?key=" + TRAFIKLAB_API_KEY
        return self.fetch_json(url).get("departures", [])

    #----------------------------------------------------------------
    #FR2 - Departure formating and display functions 
    #----------------------------------------------------------------
    @staticmethod
    def format_status(dep):
        if dep.get("canceled", False):
            return "Cancelled"
        if not dep.get("is_realtime", False):
            return "Scheduled"
        delay = dep.get("delay") or 0
        if delay >= 60:
            return "Delayed %dm" % (delay // 60)
        if delay <= -60:
            return "Early %dm" % ((-delay) // 60)
        return "On time"

    
    def update_departure_screen(self):
        self.departure_info_label.set_text("Loading departures...")

        self.departure_stop_label.set_text(
            self.selected_stop + " | " + self.transport_type
        )

        #Clear old departure information
        for row in self.departure_rows:
            for column in ("time", "line", "destination", "status"):
                row[column].set_text("")
            row["status_text"] = ""

        try:
            departures = self.get_departures()
            mode = TRANSPORT_MODES[self.transport_type]
            shown = 0

            for dep in departures:
                route = dep.get("route") or {}

                if mode and route.get("transport_mode") != mode:
                    continue

                if shown >= len(self.departure_rows):
                    break

                timestamp = dep.get("realtime") or dep.get("scheduled") or ""
                hhmm = timestamp[11:16] if len(timestamp) >= 16 else "--:--"

                line = str(
                    route.get("designation") or route.get("name") or "-"
                )

                destination = route.get("direction")
                if not destination:
                    destination = (
                        (route.get("destination") or {}).get("name") or "-"
                    )

                status = self.format_status(dep)

                #Display data in the correct row
                row = self.departure_rows[shown]
                row["time"].set_text(hhmm)
                row["line"].set_text(line[:6])
                row["destination"].set_text(str(destination)[:20])
                row["status"].set_text(status)
                row["status_text"] = status

                shown += 1

            if shown == 0:
                self.departure_info_label.set_text(
                    "No departures for selected stop/type."
                )
            else:
                self.departure_info_label.set_text(
                    "Live data: Trafiklab.se"
                )

        except Exception as error:
            log("Departure loading error: %r" % (error,))
            self.departure_info_label.set_text(
                "Trafiklab ERROR: %s" % str(error)[:50]
            )

        #Update colors for light/dark theme
        self.style_departure_screen()

    def on_stop_changed(self, event):
        self.selected_stop = event.get_target().get_selected_str()
        log("Selected stop: " + self.selected_stop)
        self.update_departure_screen()

    def on_transport_changed(self, event):
        self.transport_type = event.get_target().get_selected_str()
        log("Selected transport type: " + self.transport_type)
        self.update_departure_screen()

    # FR9 - Save settings as default

    def save_settings(self, event):
        """Saves the selected settings to ESP32 flash memory."""

        settings = {
            "transport_type": self.transport_type,
            "selected_stop": self.selected_stop
        }

        try:
            # Saves the selected settings in a JSON file.
            with open("settings.json", "w") as file:
                json.dump(settings, file)

            log("Settings saved successfully")
            self.save_status_label.set_text("Settings saved!")

        except Exception as error:
            log("Error saving settings: %r" % (error,))
            self.save_status_label.set_text("Could not save settings")

    def load_settings(self):
        """Loads previously saved default settings."""

        try:
            # Reads the saved settings from the JSON file.
            with open("settings.json", "r") as file:
                settings = json.load(file)

            valid_transports = ["Bus", "Train", "Ferry", "All"]
            valid_stops = [
                "Karlskrona Centralstation",
                "Campus Gräsvik"
            ]

            saved_transport = settings.get("transport_type")
            saved_stop = settings.get("selected_stop")

            # Restores the saved transportation type.
            if saved_transport in valid_transports:
                self.transport_type = saved_transport

            # Restores the saved stop.
            if saved_stop in valid_stops:
                self.selected_stop = saved_stop

            log("Default settings loaded successfully")

        except (OSError, ValueError, TypeError):
            log("No valid saved settings found. Using original defaults.")

    @staticmethod
    def connect_wifi():
        'Function: Connects to WiFi'
        log("connecting to Wi-Fi SSID: " + WIFI_SSID)
        station = network.WLAN(network.STA_IF)
        station.active(True)
        station.connect(WIFI_SSID, WIFI_PASSWORD)
        started = time.ticks_ms()
        while (not station.isconnected() and
               time.ticks_diff(time.ticks_ms(), started) < 15_000):
            time.sleep_ms(250)
        log("Wi-Fi connected" if station.isconnected()
            else "Wi-Fi could not connect (timeout)")


try:
    app = Application()
except Exception as error:
    log("FATAL: %r" % (error,))
    sys.print_exception(error)
    raise

