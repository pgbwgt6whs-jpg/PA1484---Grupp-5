import sys
import time
import json
import lvgl as lv
import network
import urequests

from board_lvgl import start_board
from debug_log import log


from secrets import WIFI_SSID, WIFI_PASSWORD, TRAFIKLAB_API_KEY
import secrets

API_BASE = "https://realtime-api.trafiklab.se/v1"
RESROBOT_TRIP_URL = "https://api.resrobot.se/v2.1/trip"
# These are name-search paths, not stop IDs. The stop IDs come from Stop Lookup.
# Stop IDs from Trafiklab Stop Lookup

STATUS_CHECK_INTERVAL_MS = 2000

STOP_IDS = {"Karlskrona Centralstation": "740000230", "Campus Gräsvik": "740032188", "Bergåsa station": "740001537", "Karlskrona Kungsplan": "740020510", "Karlskrona centrum": "740023372", "Karlskrona Marinmuseum": "740017997", "Verkö": "740031840"}
JOURNEY_STOPS = tuple(STOP_IDS)
TRANSPORT_MODES = {"Bus": "BUS", "Train": "TRAIN", "Ferry": "BOAT", "All": None}


class Application:
    def __init__(self):
        self.display, self.touch, self.handler = start_board()
        self.tile2_dark = False
        self.transport_type = "All" # Stores the currently selected transportation type, where "All" is used as the default value.
        self.selected_stop = "Karlskrona Centralstation"  # Stores the currently selected stop, with Karlskrona Centralstation as the default value.

        #US4.3: track the outcome of the latest API request
        self.live_data_status = "Not requested yet"
        self.last_data_update_ms = None

        self.load_settings()

        self.create_ui()
        self.connect_wifi()
        self.update_connection_status() 
        self.update_departure_screen()
        self.last_departure_update = time.ticks_ms()
        self.auto_update_timer = lv.timer_create(self.auto_update_departures, 60000, None)
        log("student application ready")


    @staticmethod
    def apply_tile_colors(tile, label, dark):
        tile.set_style_bg_opa(lv.OPA.COVER, 0)
        tile.set_style_bg_color(lv.color_hex(0x000000 if dark else 0xFFFFFF), 0)
        label.set_style_text_color(lv.color_hex(0xFFFFFF if dark else 0x000000), 0)

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
        self.tile3 = self.tileview.add_tile(2, 0, lv.DIR.LEFT | lv.DIR.RIGHT) # Tile 3 is the settings screen, so it can be swiped back to tile 2 and swiped to tile 4.
        self.tile4 = self.tileview.add_tile(3,0, lv.DIR.LEFT)

        self.tile1_label = lv.label(self.tile1)
        Intro_text = ("Public Transportation Information\n"
            "Version 2.0\n"
            "Grupp 5\n"
            "Members: Mette, Emily, \nSedra, Elsa & Ayat"
            "\nAll data is provided\nby TrafikLab")
        
        self.tile1_label.set_text(Intro_text)
        self.tile1_label.set_style_text_font(lv.font_montserrat_28, 0)
        self.tile1_label.center()
        self.apply_tile_colors(self.tile1, self.tile1_label, False)
        
        
        """US1.2B: Creating a departure screen """
        self.departure_title = lv.label(self.tile2)
        self.departure_title.set_text("DEPARTURES")
        self.departure_title.set_style_text_font(lv.font_montserrat_28, 0)
        self.departure_title.align(lv.ALIGN.TOP_LEFT, 18, 12)
        self.tile2_label = self.departure_title  # Compatibility with older UI code.

        # US4.2: a dedicated button makes a fresh request on demand.
        self.refresh_button = lv.button(self.tile3)
        self.refresh_button.set_size(118, 42)
        self.refresh_button.align(lv.ALIGN.TOP_RIGHT, -18, 10)
        self.refresh_button_label = lv.label(self.refresh_button)
        self.refresh_button_label.set_text("Refresh")
        self.refresh_button_label.center()
        self.refresh_button.add_event_cb(self.on_manual_refresh, lv.EVENT.CLICKED, None)

        self.departure_stop_label = lv.label(self.tile2)
        self.departure_stop_label.set_width(560)
        self.departure_stop_label.set_text(self.selected_stop)
        self.departure_stop_label.align(lv.ALIGN.TOP_LEFT, 20, 62)

        self.departure_headers = []
        for name, x in (("TIME", 28), ("LINE", 115), ("DESTINATION", 200), ("STATUS", 434)):
            header = lv.label(self.tile2)
            header.set_text(name)
            header.align(lv.ALIGN.TOP_LEFT, x, 101)
            self.departure_headers.append(header)

        # Fixed positions mean the columns line up with any font.
        self.departure_rows = [] # Stores the departure rows as a list of dictionaries, where each dictionary contains the panel and labels for a single departure row 
        for index in range(6): # Creates six departure rows, each with a panel and labels for time, line, destination and status
            panel = lv.obj(self.tile2) # Creates a panel for each depature row
            panel.set_size(568, 42)
            panel.align(lv.ALIGN.TOP_LEFT, 16, 127 + index * 46) # Positions each panel below the previous one, with a vertical spacing of 46 pixels 
            panel.set_style_bg_opa(lv.OPA.COVER, 0) # Sets the background opacity of the panel to fully opaque 
            panel.set_style_radius(8, 0) # Sets the corner radius of the panel to 8 pixels, giving it rounded corners 
            panel.set_style_border_width(0, 0) 
            panel.remove_flag(lv.obj.FLAG.SCROLLABLE) 
            panel.remove_flag(lv.obj.FLAG.CLICKABLE) # Removes the scrollable and clickable flags from the panel 

            row = {"panel": panel, "status_text": ""} 
            for column, x in (("time", 10), ("line", 98),("destination", 182), ("status", 417)): # Defines the x-coordinates for each column in the departure row
                label = lv.label(panel)
                label.set_text("")
                label.align(lv.ALIGN.TOP_LEFT, x, 11)
                row[column] = label
            self.departure_rows.append(row)

        self.departure_info_label = lv.label(self.tile2) 
        self.departure_info_label.set_width(560)
        self.departure_info_label.set_text("Waiting for Trafiklab...")
        self.departure_info_label.align(lv.ALIGN.TOP_LEFT, 20, 413)

        self.style_departure_screen() # Applies the selected color theme to the departure screen 
        self.tile2.add_flag(lv.obj.FLAG.CLICKABLE)
        self.tile2.add_event_cb(self.on_tile2_clicked, lv.EVENT.CLICKED, None)


        """US3.1: Create a Settings Screen"""
        # Creates the title for the settings screen. 
        self.settings_title = lv.label(self.tile3)
        self.settings_title.set_text("Settings")
        self.settings_title.set_style_text_font(lv.font_montserrat_28, 0) # Sets the front size of the settings title.
        self.settings_title.align(lv.ALIGN.TOP_MID, 0, 30) # Positions the title at the top center of the screen.

        # US4.3: two independently updated labels on the Settings screen.
        self.wifi_status_label = lv.label(self.tile3)
        self.wifi_status_label.set_width(160)
        self.wifi_status_label.align(lv.ALIGN.TOP_LEFT, 50, 78)

        self.live_data_status_label = lv.label(self.tile3)
        self.live_data_status_label.set_width(350)
        self.live_data_status_label.align(lv.ALIGN.TOP_LEFT, 230, 78)

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
        self.stop_dropdown.set_options("\n".join(JOURNEY_STOPS)) 

        # Selects the previously saved stop instead of always selecting Karlskrona Centralstation
        stops = JOURNEY_STOPS
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


        """US3.3: Enable Transportation Type Selection"""
        # Creates a label describing the transportation type dropdown.
        self.transport_label = lv.label(self.tile3)
        self.transport_label.set_text("Transport type")
        self.transport_label.align(lv.ALIGN.TOP_LEFT, 50, 150) # Positions the label on the settings screen.

        # Dropdown menu implementation
        self.transport_dropdown = lv.dropdown(self.tile3) # Creates a dropdown menu on the settings screen.
        self.transport_dropdown.set_options("Bus\nTrain\nFerry\nAll") # Adds the four transportation types required by FR8.
        transport_options = ["Bus", "Train", "Ferry", "All"]

        if self.transport_type in transport_options:
            self.transport_dropdown.set_selected(transport_options.index(self.transport_type)) # Selects the previously saved transportation type instead of always selecting "All"
        else:
            self.transport_dropdown.set_selected(3) # Selects "All" as the default option (dropdown indexes start at 0).

        self.transport_dropdown.set_width(200) # Sets the width of the dropdown menu.
        self.transport_dropdown.align(lv.ALIGN.TOP_LEFT, 250, 140) # Positions the dropdown next to the "Transport type" label.
        self.transport_dropdown.add_event_cb(self.on_transport_changed,lv.EVENT.VALUE_CHANGED, None) # Calls on_transport_changed() whenever the user selects a different transportation type.

        """FR9: Save settings button"""
        self.save_button = lv.button(self.tile3)
        self.save_button.set_size(200, 45)
        self.save_button.align(lv.ALIGN.TOP_MID, -150, 300)
        # Create text inside the save button
        self.save_button_label = lv.label(self.save_button)
        self.save_button_label.set_text("Save as default")
        self.save_button_label.center()

        self.save_button.add_event_cb(self.save_settings, lv.EVENT.CLICKED, None) # Calls save_settings() when user clicks the button
        self.save_status_label = lv.label(self.tile3) # Creates label to display confirmation message
        self.save_status_label.set_text("")
        self.save_status_label.align(lv.ALIGN.TOP_MID, 0, 390)

        """FR10 Reset settings button"""
        self.reset_button = lv.button(self.tile3)
        self.reset_button.set_size(200, 45)
        self.reset_button.align(lv.ALIGN.TOP_MID, 150, 300)
        # Creates the text inside the reset button
        self.reset_button_label = lv.label(self.reset_button)
        self.reset_button_label.set_text("Reset to default")
        self.reset_button_label.center()
        #Calls reset_settings() when the button is clicked
        self.reset_button.add_event_cb(self.reset_settings, lv.EVENT.CLICKED, None)

        # US4.3: check Wi-Fi and update elapsed-time text every 2 seconds.
        self.status_timer = lv.timer_create(self.on_status_timer, STATUS_CHECK_INTERVAL_MS, None)
        self.update_connection_status()

        """US5.1 - Journey selection screen"""
        self.journey_title = lv.label(self.tile4)
        self.journey_title.set_text("Journey selection")
        self.journey_title.set_style_text_font(lv.font_montserrat_28, 0) #Creates title with specific font for the journey selection screen
        self.journey_title.align(lv.ALIGN.TOP_MID, 0, 8)  # Move the title up to make room for results.
        #Creates a label for starting point
        self.journey_from_label = lv.label(self.tile4) 
        self.journey_from_label.set_text("From")
        self.journey_from_label.align(lv.ALIGN.TOP_LEFT, 16, 47)  # Place the From label above the left dropdown.
        #Creates a dropdown for choosing the starting point
        self.journey_from_dropdown = lv.dropdown(self.tile4)
        self.journey_from_dropdown.set_options("\n".join(JOURNEY_STOPS))
        self.journey_from_dropdown.set_selected(0)
        self.journey_from_dropdown.set_width(278)  # Leave room for long stop names.
        self.journey_from_dropdown.align(lv.ALIGN.TOP_LEFT, 16, 68)  # Align the From dropdown with its label.
        # Creates a label for the destination.
        self.journey_to_label = lv.label(self.tile4)
        self.journey_to_label.set_text("To")
        self.journey_to_label.align(lv.ALIGN.TOP_LEFT, 306, 47)  # Place the To label above the right dropdown.
        # Creates a dropdown for choosing the destination.
        self.journey_to_dropdown = lv.dropdown(self.tile4)
        self.journey_to_dropdown.set_options("\n".join(JOURNEY_STOPS))
        self.journey_to_dropdown.set_selected(1)
        self.journey_to_dropdown.set_width(278)  # Match the width of the From dropdown.
        self.journey_to_dropdown.align(lv.ALIGN.TOP_LEFT, 306, 68)  # Place the To dropdown beside the From dropdown.
         # Displays instructions for the user.
        self.journey_info_label = lv.label(self.tile4)
        self.journey_info_label.set_width(320)  # Leave space beside the message for the Search button.
        self.journey_info_label.align(lv.ALIGN.TOP_LEFT, 16, 137)  # Show details below the search status.

        """US5.2: Journey selection screen with starting stop and final destination stop"""
        self.journey_selection_label = lv.label(self.tile4) # Creates a label to diplay the selected starting stop and final destination stop 
        self.journey_selection_label.set_width(214)  # Keep search status within the left side of the row.
        self.journey_selection_label.align(lv.ALIGN.TOP_LEFT, 16, 114)  # Place search status below the stop selectors.

        """US5.3: Display matching journeys in a scrollable results panel"""
        self.journey_search_button = lv.button(self.tile4)  # Create a dedicated button for requesting journeys.
        self.journey_search_button.set_size(120, 38)  # Give the button room for a touch target and its label.
        self.journey_search_button.align(lv.ALIGN.TOP_RIGHT, -16, 114)  # Keep the button at the right of the search row.
        search_label = lv.label(self.journey_search_button)  # Attach the caption to the button.
        search_label.set_text("Search")  # Label the action that fetches journeys.
        search_label.center()  # Center the caption within the button.
        self.journey_search_button.add_event_cb(self.on_journey_search, lv.EVENT.CLICKED, None)  # Run the search only when the button is tapped.

        self.journey_results = lv.obj(self.tile4)  # Give journey cards a separate container.
        self.journey_results.set_size(568, 264)  # Reserve the lower section of the screen for results.
        self.journey_results.align(lv.ALIGN.TOP_LEFT, 16, 174)  # Place results beneath the search controls.
        self.journey_results.set_scroll_dir(lv.DIR.VER)  # Scroll the results vertically.
        self.journey_results.add_flag(lv.obj.FLAG.SCROLL_CHAIN_HOR)  # Allow horizontal tile swipes.
        self.journey_results.remove_flag(lv.obj.FLAG.SCROLL_CHAIN_VER)  # Keep vertical scroll gestures inside the results panel.
        self.journey_results.set_scrollbar_mode(lv.SCROLLBAR_MODE.AUTO)  # Show a scrollbar when the results need scrolling.
        self.journey_results.set_style_pad_all(10, 0)  # Leave space between cards and the panel edges.
        self.journey_results.set_style_pad_row(8, 0)  # Separate adjacent journey cards.
        self.journey_results.set_flex_flow(lv.FLEX_FLOW.COLUMN)  # Stack cards with room for wrapped text.

        self.journey_from_dropdown.add_event_cb(self.on_journey_changed, lv.EVENT.VALUE_CHANGED, None) # Calls on journey_changed() when the user selectes a different starting point
        self.journey_to_dropdown.add_event_cb(self.on_journey_changed, lv.EVENT.VALUE_CHANGED, None) # Calls on_journey_stop_changed() when the user selectes a different final destination

        self.on_journey_changed(None) # Updates the journey selection label with the initial starting point and final destination stop 

    def on_journey_changed(self, _event): # Updates the journey selection label when the user selects a different starting point 
        stops = JOURNEY_STOPS

        self.journey_from_stop =stops[self.journey_from_dropdown.get_selected()] # Defines the selected starting stop based on the user´s selection
        self.journey_to_stop =stops[self.journey_to_dropdown.get_selected()] # Defines the selected final destination stop bassed on the user´s selection

        if self.journey_from_stop == self.journey_to_stop: # Checks if the selected starting stop and final destination stop are the same
            self.journey_selection_label.set_text("Choose different stops")  # Explain why the Search button is disabled.
            self.journey_search_button.add_state(lv.STATE.DISABLED)  # Disable searching until the stops differ.
        else: 
            self.journey_selection_label.set_text("Ready to search")  # Indicate that the current stop pair can be searched.
            self.journey_search_button.remove_state(lv.STATE.DISABLED)  # Enable searching for a valid stop pair.
        self.journey_info_label.set_text("")  # Clear the previous message.
        self.journey_results.clean()  # Clear results for the previous stop pair.
        self.journey_results.scroll_to_y(0, lv.ANIM.OFF)  # Reset scrolling to the top for new results.

    """US5.3: Search for journeys and render the results"""
    def on_journey_search(self, _event):
        if self.journey_from_stop == self.journey_to_stop:  # Guard against an invalid search event.
            return

        self.journey_results.clean()  # Remove cards from the previous search.
        self.journey_results.scroll_to_y(0, lv.ANIM.OFF)  # Reset scrolling to the top for new results.
        try:
            journeys = self.get_matching_journeys(self.journey_from_stop, self.journey_to_stop)  # Fetch ranked results for the selected stops.
        except RuntimeError as error:  # Handle connection and response failures.
            self.journey_selection_label.set_text("Search failed")  # Distinguish a failed request from an empty result.
            self.journey_info_label.set_text(str(error))  # Show the safe message from the journey API code.
            return

        if not journeys:  # Check whether any matching public transport journeys were found.
            self.journey_selection_label.set_text("No journeys found")  # Report a successful search with no matches.
            self.journey_info_label.set_text("")  # Clear the previous message.
            return

        self.journey_selection_label.set_text("%d journey options" % len(journeys))  # Show the number of journeys displayed.
        self.journey_info_label.set_text("Data from Trafiklab.se")  # Credit the source of the journey data.
        for journey in journeys:  # Build one card for each ranked journey.
            departure = self.format_journey_time(journey["departure"])  # Format the time at the start of the journey.
            arrival = self.format_journey_time(journey["arrival"])  # Format the time at the end of the journey.
            lines = ["Departure %s    Arrival %s" % (departure, arrival)]  # Start the card with the journey times.
            if journey["transfers"]:  # Add boarding details when a vehicle change is required.
                for transfer in journey["transfers"]:  # List connections in travel order.
                    boarding_time = self.format_journey_time(transfer["departure"])  # Format the departure time of the next vehicle.
                    lines.append("Change at %s\nNext departure %s" % (transfer["stop"], boarding_time))  # Show where to board and when the next vehicle leaves.
            else:
                lines.append("Direct journey (no vehicle changes)")  # Identify journeys that require no vehicle changes.

            card = lv.label(self.journey_results)  # Add the card to the scrollable results panel.
            card.set_width(530)  # Keep text within the panel and leave room for the scrollbar.
            card.set_style_bg_color(lv.color_hex(0xE8EEF5), 0)  # Use a light background to distinguish each card.
            card.set_style_bg_opa(lv.OPA.COVER, 0)  # Make the card background visible.
            card.set_style_text_color(lv.color_hex(0x17212B), 0)  # Use dark text for contrast on the card.
            card.set_style_radius(8, 0)  # Round the card corners.
            card.set_style_pad_all(10, 0)  # Keep the text away from the card edges.
            card.set_text("\n".join(lines))  # Display the journey details on separate lines.

    @staticmethod
    def format_journey_time(timestamp):
        return "%s/%s %s" % (timestamp[8:10], timestamp[5:7], timestamp[11:16])  # Show the date for overnight trips.


    # US4.2 - Manual refresh via the existing Trafiklab pipeline.
    def on_manual_refresh(self, _event):
        """Request fresh departure data when the Refresh button is pressed."""
        log("Manual departure refresh requested")
        self.update_departure_screen()

    # US4.3 - Show real connectivity and the result of the latest fetch.
    def on_status_timer(self, _timer):
        """Refresh status labels without making an additional API request."""
        self.update_connection_status()


    # US4.3 - Show real Wi-Fi connectivity and live data status
    def update_connection_status(self):
        """Show actual Wi-Fi state and most recent Trafiklab request state."""

        connected = network.WLAN(network.STA_IF).isconnected()

        self.wifi_status_label.set_text("Wi-Fi: Connected" if connected else "Wi-Fi: Disconnected")

        if not connected:
            data_text = "Live data: Offline (no Wi-Fi)"

        elif (
            self.live_data_status in (
                "Realtime available",
                "Scheduled only",
                "No departures")
            and self.last_data_update_ms is not None):
            # Calculate time since the latest successful request
            elapsed_ms = time.ticks_diff(time.ticks_ms(), self.last_data_update_ms)

            seconds_ago = max(0, elapsed_ms // 1000)

            data_text = "Live data: %s (%ds ago)" % (self.live_data_status,seconds_ago)

        else:
            data_text = "Live data: " + self.live_data_status

        self.live_data_status_label.set_text(data_text)

    """US1.2B: Departure screen displaying live public transport departure data""" 
    #API and departure handling functions
    @staticmethod
    def fetch_json(url, timeout=None): # Fetches JSON data from the specified URL and returns it as a Python dictionary
        response = None
        try:
            if timeout is None:
                response = urequests.get(url)
            else:
                response = urequests.get(url, timeout=timeout)  # Apply a timeout when the caller supplies one.
            if response.status_code != 200:
                raise RuntimeError("Trafiklab HTTP %s" % response.status_code)
            return response.json()
        finally:
            if response is not None:
                response.close()

    def get_stop_id(self): # Returns the stop ID for the currently selected stop based on the STOP_IDS dictionary
        return STOP_IDS[self.selected_stop]

    def get_departures(self): # Fetches departure data for the currently selected stop and transportation type from the Trafiklab API and returns it as a list of departures 
        if not network.WLAN(network.STA_IF).isconnected():
            raise RuntimeError("Wi-Fi is disconnected")
        stop_id = self.get_stop_id()
        url = API_BASE + "/departures/" + stop_id + "?key=" + TRAFIKLAB_API_KEY
        return self.fetch_json(url).get("departures", [])

    """US5.3: Fetch and rank the top 5 matching journeys"""
    def get_matching_journeys(self, from_stop, to_stop):
        origin_id = STOP_IDS[from_stop]  # Map the starting stop name to its national stop ID.
        destination_id = STOP_IDS[to_stop]  # Map the destination name to its national stop ID.
        if origin_id == destination_id:  # Skip the request when both choices refer to the same stop.
            return []

        api_key = getattr(secrets, "RESROBOT_API_KEY", "").strip()  # Read the ResRobot key from local configuration.
       
        if not api_key:  # Report a missing key before trying the API.
            raise RuntimeError("ResRobot API key is missing")
        if not network.WLAN(network.STA_IF).isconnected(): # Check Wi-Fi before opening an HTTPS connection.
            raise RuntimeError("Wi-Fi is disconnected")

        url = (
            RESROBOT_TRIP_URL
            + "?format=json&numF=5&passlist=0&showPassingPoints=0"  # Omit passing stops to reduce response size.
            + "&originId=" + origin_id + "&destId=" + destination_id
            + "&accessId=" + api_key)
        
        try:
            data = self.fetch_json(url, timeout=10)  # Use a timeout for the journey request.
        except ValueError:
            message = "Invalid response from ResRobot"  # Report unreadable JSON.
        except Exception:
            message = "Could not fetch journeys from ResRobot"  # Keep the request URL out of the error message.
        else:
            return self.rank_journeys(data)  # Extract and rank journeys from the parsed response.
        raise RuntimeError(message)  # Raise outside the handler to avoid chaining the original error.

    @staticmethod
    def rank_journeys(data):
        if isinstance(data, dict) and data.get("errorCode") == "SVC_NO_RESULT":  # ResRobot can report no journeys with HTTP 200.
            return []
        if not isinstance(data, dict) or "errorCode" in data:  # Reject API errors and unexpected response types.
            raise RuntimeError("ResRobot could not plan journeys")
        if not isinstance(data.get("Trip"), list):  # A successful journey response contains a trip list.
            raise RuntimeError("Invalid journey data from ResRobot")

        journeys = []
        try:
            for trip in data["Trip"]:
                legs = trip["LegList"]["Leg"]  # Read the ordered stages of this journey.
                if not isinstance(legs, list) or not legs:  # A journey must have at least one leg.
                    raise TypeError
                vehicle_legs = [leg for leg in legs if leg["type"] == "JNY"]  # Count only public transport legs when identifying changes.
                if not vehicle_legs:  # Skip walking-only routes.
                    continue

                origin = legs[0]["Origin"]  # Include any walk before the first vehicle in the departure time.
                destination = legs[-1]["Destination"]  # Include any final walk in the arrival time.
                transfers = []  # An empty list means no vehicle changes.
                for leg in vehicle_legs[1:]:  # Each vehicle after the first is a transfer.
                    boarding_stop = leg["Origin"]  # Use the stop where the next vehicle departs.
                    transfers.append({"stop": boarding_stop["name"],  # Show the connecting vehicle's boarding stop.
                        "departure": boarding_stop["date"] + "T" + boarding_stop["time"],})

                # Keep dates with times so midnight crossings sort correctly.
                journeys.append({"departure": origin["date"] + "T" + origin["time"], "arrival": destination["date"] + "T" + destination["time"], "transfers": transfers,})

        except (KeyError, IndexError, TypeError):
            raise RuntimeError("Invalid journey data from ResRobot")

        # Sort by arrival, then transfer count, then departure.
        journeys.sort(key=lambda journey: (journey["arrival"], len(journey["transfers"]), journey["departure"]))
        return journeys[:5]  # ResRobot can return more than the requested five journeys.


    #Departure formating and display functions 
    @staticmethod
    def format_status(dep): # Formats the status of a departure based on its properties and returns a string represenation of the status 
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
        # Updates departure screen with the latest departure data
        self.departure_info_label.set_text("Loading departures...")

        # US4.3: Update status when a new API request starts
        self.live_data_status = "Loading..."
        self.update_connection_status()

        self.departure_stop_label.set_text(
            self.selected_stop + " | " + self.transport_type)

        # Clear old departure information
        for row in self.departure_rows:
            for column in ("time", "line", "destination", "status"):
                row[column].set_text("")
            row["status_text"] = ""

        try:
            departures = self.get_departures()
            mode = TRANSPORT_MODES[self.transport_type]
            shown = 0

            # US4.3: Track whether displayed departures contain realtime data
            has_realtime = False

            for dep in departures:
                route = dep.get("route") or {}

                if mode and route.get("transport_mode") != mode:
                    continue

                if shown >= len(self.departure_rows):
                    break

                timestamp = (dep.get("realtime") or dep.get("scheduled") or "")

                hhmm = (timestamp[11:16]
                    if len(timestamp) >= 16
                    else "--:--")

                line = str(route.get("designation") or route.get("name") or "-")

                destination = route.get("direction")

                if not destination:
                    destination = ((route.get("destination") or {}).get("name") or "-")

                status = self.format_status(dep)

                # Display data in the correct row
                row = self.departure_rows[shown]
                row["time"].set_text(hhmm)
                row["line"].set_text(line[:6])
                row["destination"].set_text(str(destination)[:20])
                row["status"].set_text(status)
                row["status_text"] = status

                # US4.3: Check actual realtime flag from Trafiklab
                if dep.get("is_realtime", False):
                    has_realtime = True

                shown += 1

            # US4.3: Save timestamp after successful API retrieval
            self.last_data_update_ms = time.ticks_ms()

            if shown == 0:
                # US4.3: No matching departures were found
                self.live_data_status = "No departures"

                self.departure_info_label.set_text("No departures for selected stop/type.")

            else:
                # US4.3: Determine status from actual API data
                self.live_data_status = ("Realtime available"
                    if has_realtime
                    else "Scheduled only")

                self.departure_info_label.set_text("Live data: Trafiklab.se")

        except Exception as error:
            # US4.3: Record failed API requests
            self.live_data_status = "Request failed"

            log("Departure loading error: %r" % (error,))

            self.departure_info_label.set_text("Trafiklab ERROR: %s" % str(error)[:50])

        # US4.3: Update Settings screen after API request
        self.update_connection_status()

        # Update colors for light/dark theme
        self.style_departure_screen()



    # -----------------------------------------------
    # FR3 - Automatic update of live departure data
    # -----------------------------------------------
    def auto_update_departures(self, timer):
        self.update_departure_screen()
        self.last_departure_update = time.ticks_ms() 


    def show_selection_pending(self):
        self.departure_stop_label.set_text(
            self.selected_stop + "|" + self.transport_type
        )

        # Clear old departures to avoid displaying incorrect data
        for row in self.departure_rows:
            for column in ("time", "line", "destination", "status"):
                row[column].set_text("")

            row["status_text"] = ""

        self.departure_info_label.set_text("Press refresh to load departures")

        # US4.3: Indicate that new selection has not been fetched yet
        self.live_data_status = "Waiting for refresh"
        self.last_data_update_ms = None
        self.update_connection_status()


    """ US3.2 Handel stop selection"""
    def on_stop_changed(self, event):

        stops = JOURNEY_STOPS
        index = self.stop_dropdown.get_selected() # Gets selected index
        if index >= len(stops): # Checks if index is valid
            return

        selected = stops[index] # Get selected stop
        if selected == self.selected_stop: 
            return # If there is no change in the selected stop, the function returns without any updates
        

        self.selected_stop = selected # Save the selected stop
        log("Selected stop: " + selected)
        self.show_selection_pending() # Update display without contacting Trafiklab 

    """US1.3 Handle transport type selection"""
    def on_transport_changed(self, event):
        transports = ["Bus","Train", "Ferry", "All"]
        index = self.transport_dropdown.get_selected() # Gets selected index
        if index >= len(transports): # Checks that index is valid
            return 

        selected = transports[index] # Gets transport type

        if selected == self.transport_type: 
            return # If there is no change in the selected transportation type, the funcation returns without any updates

        self.transport_type = selected # Saves transport type
        log("Selected transport type: " + selected)
        self.show_selection_pending() # Update display without contacting Trafiklab 
    
    # FR9 - Save settings as default

    def save_settings(self, event):
        #Saves the selected settings to ESP32 flash memory.

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
        #Loads previously saved default settings.

        try:
            # Reads the saved settings from the JSON file.
            with open("settings.json", "r") as file:
                settings = json.load(file)

            valid_transports = ["Bus", "Train", "Ferry", "All"]
            valid_stops = JOURNEY_STOPS

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

        #FR10 Reset setitngs to stored Defaults
    def reset_settings(self, event):
        try:
            with open("settings.json", "r") as file:  # Opens json file containing saved default settings
                settings = json.load(file)
            valid_transports = ["Bus", "Train", "Ferry", "All"]
            valid_stops = JOURNEY_STOPS
            saved_transport = settings.get("transport_type") #Reads previously saved default settings
            saved_stop = settings.get("selected_stop")
            if (saved_transport not in valid_transports or saved_stop not in valid_stops): #Checks if both saved values are valid
                raise ValueError("Invalid saved settings")
            self.transport_type = saved_transport #Restores the saved transportation type
            self.selected_stop = saved_stop #Restores the saved stop
            self.transport_dropdown.set_selected(valid_transports.index(self.transport_type)) #Updates the transportation type dropdown
            self.stop_dropdown.set_selected(valid_stops.index(self.selected_stop))
            self.show_selection_pending()
            #Display confirmation message
            log("Settings reset to stored defaults")
            self.save_status_label.set_text("Settings reset!")
        except (OSError, ValueError, TypeError) as error:
            log("Could not reset settigs: %r" % (error,))
            self.save_status_label.set_text("No saved defaults found")
    
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

