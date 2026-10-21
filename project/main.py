import sys
import time

import lvgl as lv
import network

from board_lvgl import start_board
from debug_log import log

from secrets import WIFI_SSID, WIFI_PASSWORD


class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()
        self.tile2_dark = False
        self.transport_type = "All" # Stores the currently selected transportation type, where "All" is used as the default value.
        self.selected_stop = "Karlskrona Centralstation"  # Stores the currently selected stop, with Karlskrona Centralstation as the default value.

        self.create_ui()
        self.connect_wifi()
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
        self.apply_tile_colors(self.tile2, self.tile2_label, self.tile2_dark)

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
            "Members: Mette, Emily, Sedra, Elsa and Ayat"
        )
        self.tile1_label.set_text(Intro_text)
        self.tile1_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile1_label.center()
        self.apply_tile_colors(self.tile1, self.tile1_label, False)

        self.tile2_label = lv.label(self.tile2)
        self.tile2_label.set_text("Welcome to the workshop")
        self.tile2_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile2_label.center()
        self.apply_tile_colors(self.tile2, self.tile2_label, False)
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
        self.stop_dropdown.set_options(
             "Karlskrona Centralstation\n"
             "Campus Gräsvik"
        )  # Adds the available stops to the dropdown menu.    

        self.stop_dropdown.set_selected(0)  # Selects "Karlskrona Centralstation" as the default stop (dropdown indexes start at 0).  
        self.stop_dropdown.set_width(250)  # Sets the width of the stop dropdown menu.
        self.stop_dropdown.align(lv.ALIGN.TOP_LEFT, 250, 210)  # Positions the stop dropdown next to the "Select stop" label.

        self.stop_dropdown.add_event_cb(
            self.on_stop_changed,
            lv.EVENT.VALUE_CHANGED,
            None
        )  # Calls on_stop_changed() when the user selects a different stop.



        # Transportation type selection - FR8
        # Creates a label describing the transportation type dropdown.
        self.transport_label = lv.label(self.tile3)
        self.transport_label.set_text("Transport type")
        self.transport_label.align(lv.ALIGN.TOP_LEFT, 50, 150) # Positions the label on the settings screen.

        # Dropdown menu implementation
        self.transport_dropdown = lv.dropdown(self.tile3) # Creates a dropdown menu on the settings screen.
        self.transport_dropdown.set_options("Bus\nTrain\nFerry\nAll") # Adds the four transportation types required by FR8.
        self.transport_dropdown.set_selected(3) # Selects "All" as the default option (dropdown indexes start at 0).
        self.transport_dropdown.set_width(200) # Sets the width of the dropdown menu.
        self.transport_dropdown.align(lv.ALIGN.TOP_LEFT, 250, 140) # Positions the dropdown next to the "Transport type" label.
        self.transport_dropdown.add_event_cb(self.on_transport_changed,lv.EVENT.VALUE_CHANGED, None) # Calls on_transport_changed() whenever the user selects a different transportation type.

    def on_stop_changed(self, event):
        """Updates the selected stop."""
        dropdown = event.get_target() # Gets the dropdown object that triggered the event.
        self.selected_stop = dropdown.get_selected_str() # Gets and stores the selected stop.
        log("Selected stop: " + self.selected_stop) # Prints the selected stop to the log for testing


    def on_transport_changed(self, event):
        dropdown = event.get_target() # Gets the dropdown object that triggered the event.
        self.transport_type = dropdown.get_selected_str() # Gets the selected option as text and stores it in the transport_type variable.
        log("Selected transport type: "+ self.transport_type) # Prints the selected transportation type to the log (useful for dropdown testing).


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
