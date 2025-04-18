import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk,Canvas,messagebox,Entry, Button
import threading
import subprocess
import os
from PIL import Image, ImageTk
from cefpython3 import cefpython as cef
import sys
import pandas as pd
from gwpy.timeseries import TimeSeries
import json
import logging
from PIL import Image, ImageTk
from gwosc.datasets import find_datasets, event_gps
from gwosc.locate import get_event_urls
from gwpy import time as gp_time
from gwosc import datasets
from datetime import datetime
from gwpy.timeseries import TimeSeries
from scipy.signal import get_window
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import csv

# Configure logging
logging.basicConfig(
    filename="omicron_plot.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
HISTORY_FILE = "gravfetch_history.json"  # Define history file


class Application:
    
    def __init__(self, root):
        self.root = root
        self.root.title("GWEasy")
        self.root.geometry("1024x768")
        # Setup the main notebook (tab structure)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        
        # Configure root window to allow resizing
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.gwosc_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.gwosc_tab, text="GWOSCRef")
        self.gwosc_tab = GWOSCApp(self.gwosc_tab,self.root)
        # Add the first tab for script execution (Gravfetch)
        self.gravfetch_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.gravfetch_tab, text="Gravfetch")

        # Add the second tab for OMICRON
        self.omicron_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.omicron_tab, text="OMICRON")
        
        # Omiviz Tab (NEW)
        self.omiviz_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.omiviz_tab, text="Omiviz")
     
        self.TimeSeriesWav = ttk.Frame(self.notebook)
        self.notebook.add(self.TimeSeriesWav, text="TimeSeriesWav")

        self.FFT = ttk.Frame(self.notebook)
        self.notebook.add(self.FFT, text="FFT")

        self.PSDs = ttk.Frame(self.notebook)
        self.notebook.add(self.PSDs, text="Power Spectral Density")

        self.Spectrogram = ttk.Frame(self.notebook)
        self.notebook.add(self.Spectrogram, text="Spectrogram")

        # Initialize both GUIs (Gravfetch and OMICRON) in their respective tabs
        self.gravfetch_app = GravfetchApp(self.gravfetch_tab)
        self.omicron_app = OmicronApp(self.omicron_tab)
        self.omiviz_app = Omiviz(self.omiviz_tab)  # Add Omiviz GUI
        self.TimeSeriesWav_app = TimeSrswaveform(self.TimeSeriesWav) 
        self.FFT = FFT(self.FFT)
        self.PSDs = PSDs(self.PSDs)
        self.Spectrogram=Spectrogram(self.Spectrogram)
         
        
class TerminalFrame(tk.Frame):
    def __init__(self, parent, row, column, rowspan=1, columnspan=1, height=15, width=100):
        super().__init__(parent)

        # Configure terminal output widget
        self.output_text = scrolledtext.ScrolledText(self, wrap=tk.WORD, 
                                                     bg="black", fg="white",
                                                     font=("Courier", 10),
                                                     height=height, width=width)
        self.output_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.output_text.config(state="disabled")  # Prevent user editing
        # Place frame using grid
        self.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan, sticky="nsew", padx=10, pady=10)

    def append_output(self, text, color="white"):
        """Append text to the terminal and auto-scroll."""
        self.output_text.config(state="normal")
        self.output_text.insert(tk.END, text + "\n")
        self.output_text.yview(tk.END)  # Auto-scroll to latest output
        self.output_text.config(state="disabled")


class OmicronApp:
    def __init__(self, root):
        self.root = root
        self.config_path = "config.txt"
        self.config_data = {}
        self.entries = {}
        self.output_products = {}
        self.ui_elements = {}
       
        self.project_dir = os.getcwd().replace("\\", "/")  
        self.wsl_project_dir = f"/mnt/{self.project_dir[0].lower()}/{self.project_dir[2:]}"  
        print(f"WSL Project Directory: {self.wsl_project_dir}")  # Debugging output
        self.GWFOUT_DIRECTORY = "./gwfout"
   
        # Scrollable Frame
        self.canvas = tk.Canvas(root)
        self.scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.window_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Terminal Output
        # Use shared terminal frame
        self.terminal = TerminalFrame(self.root, row=4, column=0, columnspan=2, height=10, width=80)  # Pass the shared terminal instance
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        self.create_widgets()
        self.load_config()
    def create_widgets(self):
        self.create_channel_dropdown(row=1)
        self.create_file_selector("Select .ffl File:", "DATA FFL",row=2,column=0)
        self.create_editable_dropdown("Sampling Frequency:", "DATA SAMPLEFREQUENCY", ["1024", "2048", "4096"], row=3, column=0)

        # Ensure proper column expansion
        for i in range(4):
            self.scrollable_frame.grid_columnconfigure(i, weight=1)


        # Button Frame
        button_frame = tk.Frame(self.scrollable_frame,bd=2, relief="groove", padx=5, pady=5)
        button_frame.grid(row=10, column=0, columnspan=4, pady=10, sticky="ew")
        self.custom_segs_btn = tk.Button(button_frame, text="Custom Segs", command=self.open_custom_segs_dialog)
        self.custom_segs_btn.pack(side="left", padx=20)  # Adjust position as needed
        self.save_button = tk.Button(button_frame, text="Save Config", command=self.save_config)
        self.save_button.pack(side="left", padx=20)  
        self.start_button = tk.Button(button_frame, text="Start OMICRON", command=self.run_omicron_script)
        self.start_button.pack(side="left", padx=20)  
       
        # Parameter Frame
        param_frame = tk.Frame(self.scrollable_frame,bd=2, relief="groove", padx=5, pady=5)
        param_frame.grid(row=11, column=0, columnspan=4, pady=10, sticky="ew")
        self.create_double_entry("Timing:", "PARAMETER TIMING", param_frame, 0, 0)
        self.create_double_entry("Frequency Range:", "PARAMETER FREQUENCYRANGE", param_frame, 0, 10)
        self.create_double_entry("Q-Range:", "PARAMETER QRANGE", param_frame, 1, 0)
        self.create_entry("Mismatch Max:", "PARAMETER MISMATCHMAX", param_frame, 1, 10)
        self.create_entry("SNR Threshold:", "PARAMETER SNRTHRESHOLD", param_frame, 2, 0)
        self.create_entry("PSD Length:", "PARAMETER PSDLENGTH", param_frame, 2, 10)
        # Output Frame
        output_frame = tk.Frame(self.scrollable_frame, bd=2, relief="groove", padx=5, pady=5)
        output_frame.grid(row=12, column=0, columnspan=4, pady=10, sticky="ew")
        self.create_folder_selector("Select Output Directory:", "OUTPUT DIRECTORY", is_directory=True, frame=output_frame,row=13,column=0)
        self.create_output_products_selection(output_frame, row=14, column=0)
        self.create_dropdown("Select Format:", "OUTPUT FORMAT", ["root", "hdf5", "Format3"], frame=output_frame,row=15,column=0)
        self.create_slider("Verbosity (0-3):", "OUTPUT VERBOSITY", 0, 3, frame=output_frame,row=16,column=0)


    #Parameters entry 
    def create_entry(self, label, key, frame=None, row=0, col=0):
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=col, sticky="w", padx=5, pady=5)
        var = tk.StringVar(value=self.config_data.get(key, ""))
        entry = tk.Entry(target_frame, textvariable=var, width=15)  # Uniform width
        entry.grid(row=row, column=col + 1, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = var

    def create_double_entry(self, label, key, frame=None, row=0, col=0):
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=col, sticky="w", padx=5, pady=5)
        var1 = tk.StringVar()
        var2 = tk.StringVar()
        entry_width = 15  # Same width for both fields
        entry1 = tk.Entry(target_frame, textvariable=var1, width=entry_width)
        entry2 = tk.Entry(target_frame, textvariable=var2, width=entry_width)
        entry1.grid(row=row, column=col + 1, sticky="ew", padx=5, pady=5)
        entry2.grid(row=row, column=col + 2, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = (var1, var2)

    #Output fields 
    def create_file_selector(self, label, key, is_directory=False, frame=None,row=0,column=0):
        """Creates a file/directory selector inside the given frame (or default to scrollable_frame)."""
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=column, sticky="w", padx=5, pady=5)
        var = tk.StringVar(value=self.config_data.get(key, ""))  # Preserve previous selection
        button = tk.Button(target_frame, text="Select", command=lambda: self.select_file(var))
        button.grid(row=row, column=2,columnspan=5, padx=5, pady=5)
        entry = tk.Entry(target_frame, textvariable=var, width=40, state="readonly")
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = var

    def create_folder_selector(self, label, key, is_directory=False, frame=None, row=0, column=0):
        """Creates a file/directory selector inside the given frame (or default to scrollable_frame).
        Ensures paths are relative to the current working directory and creates the directory if missing.
        Returns the selected relative path.
        """
        target_frame = frame if frame else self.scrollable_frame
        
        # Label for the field
        tk.Label(target_frame, text=label).grid(row=row, column=column, sticky="w", padx=5, pady=5)

        # Get stored path or set a default
        var = tk.StringVar(value=self.config_data.get(key, ""))
        dir_path = var.get().strip()

        if not dir_path:
            # Default output directory: "./OmicronOut"
            dir_path = os.path.join(os.getcwd(), "OmicronOut")

        # Convert to absolute, then to a relative path
        abs_path = os.path.abspath(dir_path)
        rel_path = os.path.relpath(abs_path, os.getcwd())

        # Ensure the relative path uses Unix-style slashes and starts with "./" or "../"
        rel_path = rel_path.replace("\\", "/")
        if not rel_path.startswith(".") and not rel_path.startswith(".."):
            rel_path = f"./{rel_path}"

        var.set(rel_path)

        # Ensure directory exists
        if not os.path.exists(abs_path):
            os.makedirs(abs_path, exist_ok=True)
            self.append_output(f"Created missing directory: {rel_path}\n")

        # Readonly Entry Field to display selected path
        entry = tk.Entry(target_frame, textvariable=var, width=50, state="readonly")
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)

        # Select Button for File/Folder
        button = tk.Button(target_frame, text="Select", command=lambda: self.select_file(var, is_directory))
        button.grid(row=row, column=2, padx=5, pady=5)

        # Store the variable reference
        self.ui_elements[key] = var
        
        # Return the selected relative path
        return rel_path

    def create_output_products_selection(self, frame=None, row=0, column=0):
        """Creates checkboxes for selecting output products inside a given frame."""
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text="Select Output Products:").grid(row=row,column=column, sticky="w", padx=5, pady=5)
        self.ui_elements["OUTPUT PRODUCTS"] = {}
        product_options = ["triggers", "html"]
        for idx, product in enumerate(product_options):
            var = tk.BooleanVar(value=product in self.config_data.get("OUTPUT PRODUCTS", ""))
            chk = tk.Checkbutton(target_frame, text=product, variable=var)
            chk.grid(row=row, column=idx+1, sticky="w", padx=5)
            self.ui_elements["OUTPUT PRODUCTS"][product] = var
            print(idx)

    def create_dropdown(self, label, key, options, frame=None,row=0,column=0):
        """Creates a dropdown menu inside a given frame."""
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=column,columnspan=5, sticky="w", padx=5, pady=5)
        var = tk.StringVar(value=self.config_data.get(key, options[0]))
        dropdown = ttk.Combobox(target_frame, textvariable=var, values=options)
        dropdown.grid(row=row, column=column+1, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = var

    def create_editable_dropdown(self, label, key, options, frame=None, row=0, column=0):
        """Creates an editable dropdown menu inside a given frame."""
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=column, columnspan=5, sticky="w", padx=5, pady=5)

        var = tk.StringVar(value=self.config_data.get(key, options[0]))
        dropdown = ttk.Combobox(target_frame, textvariable=var, values=options, state="normal")  # Enable text input
        dropdown.grid(row=row, column=column+1, sticky="ew", padx=5, pady=5)

        self.ui_elements[key] = var  # Store variable for config access

        return dropdown  # Return the dropdown so it can be modified if needed


    def create_slider(self, label, key, min_val, max_val, frame=None,row=0,column=0):
        """Creates a slider for selecting a numerical value."""
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=column, sticky="w", padx=5, pady=5)
        var = tk.IntVar(value=self.config_data.get(key, min_val))
        slider = tk.Scale(target_frame, from_=min_val, to=max_val, orient="horizontal", variable=var)
        slider.grid(row=row, column=column+1, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = var

    def create_channel_dropdown(self, row=0):
        """Creates an editable dropdown for selecting a channel, updating dynamically in the background."""

        # Label
        tk.Label(self.scrollable_frame, text="Select Channel:").grid(row=row, column=0, sticky="w")

        # StringVar for dropdown
        self.ui_elements["DATA CHANNELS"] = tk.StringVar()

        # Create an editable dropdown
        self.channel_dropdown = ttk.Combobox(
            self.scrollable_frame,
            textvariable=self.ui_elements["DATA CHANNELS"],
            values=[],  # Start empty, will be populated dynamically
            state="normal"  # Allows manual input
        )
        self.channel_dropdown.grid(row=row, column=1, sticky="ew")

        # Function to fetch available channels
        def populate_channels():
            """Get available channels from the directory and saved history."""
            base_path = self.GWFOUT_DIRECTORY
            history_file = "gravfetch_history.json"
            channels = set()

            default_structure = {"gwfout_path": str(base_path), "channels": []}

            if not os.path.exists(history_file):
                with open(history_file, "w") as file:
                    json.dump(default_structure, file, indent=4)
                print(f"Created missing history file: {history_file}")

            try:
                with open(history_file, "r") as file:
                    history_data = json.load(file)

                if not isinstance(history_data, dict) or "channels" not in history_data:
                    history_data = default_structure
                    with open(history_file, "w") as file:
                        json.dump(history_data, file, indent=4)
                    print(f"Fixed malformed history file: {history_file}")

                channels.update(history_data["channels"])

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"Warning: History file corrupted, resetting: {e}")
                history_data = default_structure
                with open(history_file, "w") as file:
                    json.dump(history_data, file, indent=4)

            if os.path.exists(base_path) and os.path.isdir(base_path):
                for d in os.listdir(base_path):
                    dir_path = os.path.join(base_path, d)
                    if os.path.isdir(dir_path):
                        if d.count(":") > 1:
                            d = d[:d.find(":", d.find(":") + 1)].replace(":", "_") + d[d.find(":", d.find(":") + 1):]
                        channels.add(d)

            return sorted(channels) if channels else ["No Channels Available"]

        # Function to update the channel list in the background
        def update_channel_options():
            """Update the dropdown values without affecting user input."""
            current_input = self.ui_elements["DATA CHANNELS"].get()  # Get user input
            channel_options = populate_channels()  # Get the latest channel list

            # Update only the dropdown values without resetting user input
            self.channel_dropdown['values'] = channel_options

            # Do NOT modify the user's input, just update the dropdown options
            self.scrollable_frame.after(4000, update_channel_options)  # Refresh every 4 seconds

        # Start the update process in the background
        update_channel_options()

        return self.channel_dropdown


    def select_file(self, var, is_directory=False):
        file_path = filedialog.askdirectory() if is_directory else filedialog.askopenfilename()
        if file_path:
            relative_path = os.path.relpath(file_path, os.getcwd())  # Convert to relative path
            var.set(relative_path)
            print(f"FFL file selected: {relative_path}")  # DEBUGGING

    def load_config(self):
        try:
            with open(self.config_path, 'r') as file:
                for line in file:
                    parts = line.strip().split("\t")
                    if len(parts) == 2:
                        self.config_data[parts[0]] = parts[1]
        except FileNotFoundError:
            self.append_output("Config file not found. Using defaults.\n")

    def save_config(self):
        base_path = os.getcwd().replace("\\", "/")  # Get current working directory with forward slashes
        with open(self.config_path, 'w', encoding='utf-8') as file:
            for key, var in self.ui_elements.items():
                if isinstance(var, tuple):  # For double-entry fields
                    value = f"{var[0].get()} {var[1].get()}"
                elif isinstance(var, dict):  # For multiple selections (checkboxes)
                    selected_products = [prod for prod, v in var.items() if v.get()]
                    value = " ".join(selected_products)
                else:
                    value = var.get()
                if key == "DATA CHANNELS":
                    parts = value.split("_", 1)  # Split at the first underscore
                    #if len(parts) == 2:
                        #value = parts[0] + ":" + parts[1]  # Replace only the first underscore with a colon
                # Convert absolute paths to relative paths based on current directory
                if key in ["DATA FFL", "OUTPUT DIRECTORY"]:  
                    print(key)  # Debugging
                    if value:
                        value = value.replace("\\", "/")  
                        abs_path = os.path.abspath(value).replace("\\", "/")  # Ensure absolute path uses `/`
                        if abs_path.startswith(base_path):  
                            rel_path = os.path.relpath(abs_path, base_path).replace("\\", "/")  # Convert to relative path
                            if not rel_path.startswith(".") and not rel_path.startswith(".."):
                                rel_path = f"./{rel_path}"
                            value = rel_path  # Assign the corrected relative path
                            print("Relative Path:", value)  # Debugging
                            print("Absolute Path:", abs_path)  # Debugging

                # Reconstruct the formatted line
                if key.startswith("DATA "):
                    formatted_line = f"{key}\t{value}\n"
                elif key.startswith("PARAMETER "):
                    formatted_line = f"PARAMETER\t{key.split()[1]}\t{value}\n"
                elif key.startswith("OUTPUT "):  
                
                    formatted_line = f"OUTPUT\t{key.split()[1]}\t{value}\n"
                else:
                    formatted_line = f"{key}\t{value}\n"

                print(f"Saving to config: {formatted_line.strip()}")  # Debugging
                file.write(formatted_line)

        self.append_output(f"Config file saved at '{self.config_path}' with the correct format.\n")
        
        messagebox.showinfo("Success", "Configuration has been saved successfully!")

    def run_omicron_script(self):
        """Start the OMICRON script in a separate process and update the output in real-time."""
        self.append_output("Starting OMICRON script...\n")
        
        # Start the OMICRON process in a new thread to avoid blocking the GUI
        omicron_thread = threading.Thread(target=self.start_omicron_process, daemon=True)
        omicron_thread.start()
    
    def start_omicron_process(self):
        """Run the OMICRON command dynamically in WSL."""
        try:
            # Get the selected FFL file from UI
            ffl_file = self.ui_elements.get("DATA FFL", "").get().strip()
            if not ffl_file or not os.path.exists(ffl_file):
                self.append_output("Error: No valid .ffl file selected.\n")
                return

            # Extract first and last time segment from the .ffl file
            with open(ffl_file, "r") as f:
                lines = [line.strip().split() for line in f if line.strip()]
            
            if not lines or len(lines[0]) < 2 or len(lines[-1]) < 2:
                self.append_output("Error: Invalid .ffl file format.\n")
                return

            first_time_segment = lines[0][1]
            last_time_segment = lines[-1][1]

            # Construct the OMICRON command
            omicron_cmd = f"omicron {first_time_segment} {last_time_segment} ./config.txt > omicron.out 2>&1"

            # Full WSL command (fixing conda initialization issue)
            wsl_command = 'wsl bash -ic "' + omicron_cmd + '"'
            self.append_output(f"Running: {wsl_command}\n")

            # Run command asynchronously with real-time output capture
            process = subprocess.Popen(
                wsl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )

            # Stream output dynamically to the terminal
            while True:
                output = process.stdout.readline()
                if output == "" and process.poll() is not None:
                    break
                if output:
                    self.append_output(output)

            while True:
                error = process.stderr.readline()
                if error == "" and process.poll() is not None:
                    break
                if error:
                    self.append_output(f"ERROR: {error}")

            process.wait()
            if process.returncode != 0:
                self.append_output(f"Error: Command failed with return code {process.returncode}.\n")
            else:
                self.append_output("OMICRON process completed successfully.\n")

        except Exception as e:
            self.append_output(f"Unexpected error: {e}\n")

    def append_output(self, text):
        """Append output to the shared terminal frame."""
        self.terminal.append_output(text)
        
    def open_custom_segs_dialog(self):
        """Opens a GUI window to select a channel and time segments with scrolling and dynamic layout."""
        channel_dir = filedialog.askdirectory(initialdir="./gwfout", title="Select Channel Directory")
        if not channel_dir:
            return

        segments = [d for d in os.listdir(channel_dir) if os.path.isdir(os.path.join(channel_dir, d))]
        if not segments:
            messagebox.showerror("Error", "No time segments found in selected channel.")
            return

        # Create the selection window
        selection_window = tk.Toplevel(self.root)
        selection_window.title("Select Time Segments")
        selection_window.geometry("400x400")  # Adjustable window size

        # Header label
        tk.Label(selection_window, text="Select Time Segments:", font=("Arial", 12)).pack(pady=5)

        # Create canvas inside a frame with scrollbar
        container = tk.Frame(selection_window)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Checkbox variables and widgets
        selected_segments = {}
        for idx, segment in enumerate(segments):
            selected_segments[segment] = tk.BooleanVar()
            chk = tk.Checkbutton(scrollable_frame, text=segment, variable=selected_segments[segment])
            chk.grid(row=idx, column=0, sticky="w", padx=5, pady=2)

        # Bottom button frame (always visible)
        bottom_frame = tk.Frame(selection_window)
        bottom_frame.pack(fill="x", pady=10)

        def confirm_selection():
            selected = [seg for seg, var in selected_segments.items() if var.get()]
            if not selected:
                messagebox.showerror("Error", "No segments selected.")
            else:
                self.generate_fin_ffl(channel_dir, selected)
                selection_window.destroy()

        def toggle_all():
            all_selected = all(var.get() for var in selected_segments.values())
            for var in selected_segments.values():
                var.set(not all_selected)

        tk.Button(bottom_frame, text="Confirm", command=confirm_selection).pack(side="left", padx=20)
        tk.Button(bottom_frame, text="Toggle All", command=toggle_all).pack(side="right", padx=20)

    def generate_fin_ffl(self, channel_dir, selected_segments):
        """ Generates fin.ffl file with correctly formatted paths and timestamps, then preselects it in the UI. """
        fin_ffl_path = os.path.join(channel_dir, "fin.ffl")
        
        with open(fin_ffl_path, "w") as ffl_file:
            for segment in selected_segments:
                segment_path = os.path.join(channel_dir, segment)
                gwf_files = [file for file in os.listdir(segment_path) if file.endswith(".gwf")]
                if not gwf_files:
                    continue  # Skip if no GWF files
                gwf_file_path = os.path.join(segment_path, gwf_files[0])
                gwf_file_path = os.path.relpath(gwf_file_path, start=".")  # Truncate path to start from `./`
                gwf_file_path = gwf_file_path.replace("\\", "/")  # Convert \ to /
                segment_parts = segment.split("_")
                start_time = segment_parts[0]  # Use the first timestamp as is
                duration = int(segment_parts[1]) - int(segment_parts[0])  # Calculate duration
                ffl_file.write(f"./{gwf_file_path} {start_time} {duration} 0 0\n")

        # **Automatically select the generated fin.ffl file**
        relative_ffl_path = os.path.relpath(fin_ffl_path, os.getcwd()).replace("\\", "/")
        self.ui_elements["DATA FFL"].set(relative_ffl_path)
        messagebox.showinfo("Success", f"fin.ffl created and selected: {relative_ffl_path}")

class GravfetchApp:
    def __init__(self, root):
        self.root = root
        self.time_csv_file = ""
        self.channel_csv_file = ""
        self.execution_running = False
        self.process = None
        self.gwfout_path = "./gwfout/"
        self.loaded_channels = []  # Store previously used channels

        # Load previous selections from JSON if available
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r") as f:
                    history_data = json.load(f)
                    self.gwfout_path = history_data.get("gwfout_path", "./gwfout/")
                    self.loaded_channels = history_data.get("channels", [])
            except json.JSONDecodeError:
                print("Error reading history file, starting fresh.")
        # Setup Execution Tab
        self.setup_execution_tab()

        # Create Terminal (Placed in row 4, column 0)
        self.terminal = TerminalFrame(self.root, row=5, column=0, columnspan=2, height=20, width=80)

    def setup_execution_tab(self):
        """Sets up the Execution tab with buttons, output terminal, etc."""
        # Status bar frame at the top
        self.status_bar_frame = tk.Frame(self.root, bg="lightgray")
        self.status_bar_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        
        # Label for the status bar
        self.status_label = tk.Label(self.status_bar_frame, text="Idle", fg="black", bg="lightgray", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # File selection buttons
        self.time_button = tk.Button(self.root, text="Select Time CSV", command=self.select_time_csv)
        self.time_button.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.channel_button = tk.Button(self.root, text="Select Channel CSV", command=self.select_channel_csv)
        self.channel_button.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.gwf_button = tk.Button(self.root, text="Select Output (GWF) Dir", command=self.select_gwfout_dir)
        self.gwf_button.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        
        # Start/Stop button
        self.start_stop_button = tk.Button(self.root, text="Start Execution", command=self.toggle_execution)
        self.start_stop_button.grid(row=4, column=0, padx=10, pady=10, sticky="ew")

        self.root.grid_rowconfigure(5, weight=1)  # Make terminal expandable
        self.root.grid_columnconfigure(0, weight=1)  # Ensure alignment

    def select_time_csv(self):
        """Open file dialog for time CSV file."""
        self.time_csv_file = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        self.status_label.config(text=f"Selected Time CSV: {self.time_csv_file}")
    
    def select_channel_csv(self):
        """Open file dialog for channel CSV file."""
        self.channel_csv_file = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        self.status_label.config(text=f"Selected Channel CSV: {self.channel_csv_file}")
    
    def select_gwfout_dir(self):
        """Open file dialog for output dir (folder) selection."""
        self.gwfout_path = filedialog.askdirectory()  # Use askdirectory instead of askopenfilename
        if self.gwfout_path:  # Check if a directory was selected
            self.status_label.config(text=f"Selected Output Dir: {self.gwfout_path}")
            self.gwfout_path = self.gwfout_path
        else:
            self.status_label.config(text="No directory selected", fg="red")
 

    def toggle_execution(self):
        """Start or stop the execution of the Gravfetch script."""
        if self.execution_running:
            self.execution_running = False
            self.start_stop_button.config(text="Start Execution")
            self.status_label.config(text="Execution Stopped", fg="red")
            self.append_output("Execution stopped.\n")

            if self.process:
                self.process.terminate()
                self.process = None
        else:
            if not self.time_csv_file or not self.channel_csv_file:
                self.append_output("Please select both CSV files.\n")
                return
            
            self.execution_running = True
            self.start_stop_button.config(text="Stop Execution")
            self.status_label.config(text="Execution Started", fg="green")
            self.append_output("Execution started...\n")

            # Start the execution in a separate thread to avoid blocking the GUI
            self.execution_thread = threading.Thread(target=self.run_gravfetch_script, daemon=True)
            self.execution_thread.start()

    def run_gravfetch_script(self):
        """Runs the Gravfetch script logic directly within the GUI."""
        try:
            # Ensure the input path exists
            if not os.path.exists(self.gwfout_path):
                print(f"The path {self.gwfout_path} does not exist. Creating the path...")
                os.makedirs(self.gwfout_path)

            # Load the CSV files (time ranges and channel data)
            time_ranges = pd.read_csv(self.time_csv_file, header=None, names=["start", "end"])
            channels = pd.read_csv(self.channel_csv_file, header=None, skiprows=1, names=["Channel", "Sample Rate"])

            # Debug: Check the loaded data
            print("Loaded time ranges:")
            print(time_ranges)
            print("Loaded channels:")
            print(channels)

            # Get the current working directory (dynamic path)
            current_dir = os.getcwd()

            # Process data for each channel
            self.loaded_channels = []  # Reset before fetching
            for _, channel_row in channels.iterrows():
                channel_name = channel_row['Channel']
                self.loaded_channels.append(channel_name)  # Store the channel name
                sampling_rate = channel_row['Sample Rate']
                print(f"Processing channel: {channel_name}")

                # Create a directory for the channel within the input path
                channel_dir = os.path.join(self.gwfout_path, channel_name.replace(":", "_"))  # Replace ':' with '_'
                os.makedirs(channel_dir, exist_ok=True)
                print(f"Created channel directory: {channel_dir}")

                # Create a separate fin.ffl file for each channel inside its directory
                fin_file_path = os.path.join(channel_dir, "fin.ffl")

                # Open the channel-specific fin.ffl file for appending
                with open(fin_file_path, 'a') as fin:
                    for _, time_row in time_ranges.iterrows():
                        start_time = int(time_row["start"])
                        end_time = int(time_row["end"])

                        # Try fetching data, skip if error occurs
                        try:
                            print(f"Fetching data for channel '{channel_name}' from {start_time} to {end_time}...")
                            # Fetch data from GWPy
                            data = TimeSeries.fetch(channel_name, start=start_time, end=end_time, host='nds.gwosc.org')

                            # Create a subfolder for the time range within the channel folder
                            time_dir_path = os.path.join(channel_dir, f"{start_time}_{end_time}")
                            os.makedirs(time_dir_path, exist_ok=True)
                            print(f"Created time directory: {time_dir_path}")

                            # File path to save the GWF file
                            output_file = os.path.join(time_dir_path, f"{channel_name.replace(':', '_')}_{start_time}_{end_time}.gwf")

                            # Save the strain data in `gwf` format
                            data.write(output_file)
                            print(f"Aux data for channel '{channel_name}' from {start_time} to {end_time} saved to {output_file}")

                            # Extract relevant data for fin.ffl
                            t0 = data.t0  # Start time (gps_start_time)
                            dt = end_time - start_time  # Duration of the data (file_duration)
                            print(f"Data start time: {t0}, Duration: {dt}")

                            # Convert backslashes to double forward slashes for fin.ffl
                            relative_path = os.path.relpath(output_file, current_dir).replace("\\", "")

                            # Write the information to the channel-specific fin.ffl file
                            fin.write(f"./{relative_path} {start_time} {dt} 0 0\n")
                            print(f"Added to {fin_file_path}: ./{relative_path} {start_time} {dt} 0 0")

                        except RuntimeError as e:
                            # If data fetching fails, log the error and continue with the next time segment
                            print(f"Error fetching data for {channel_name} from {start_time} to {end_time}: {e}")
                            continue  # Skip to the next time segment

            # Notify user of completion
            self.append_output("All channel-specific fin.ffl files created.\n")
            self.append_output("Data fetching and file creation completed successfully.\n")

            # Update status
            self.execution_running = False
            self.start_stop_button.config(text="Start Execution")
            self.status_label.config(text="Execution Finished", fg="green")
            self.save_channel_history()
            self.append_output("Execution finished.\n")

        except Exception as e:
            # Handle any errors that occur during execution
            self.append_output(f"Error running the script: {e}")
            self.execution_running = False
            self.start_stop_button.config(text="Start Execution")
            self.status_label.config(text="Execution Failed", fg="red")
            self.append_output("Execution failed.\n")
        
    def append_output(self, text):
        """Send output to the terminal"""
        self.terminal.append_output(text)
    def save_channel_history(self):
        """Save the selected channels to a JSON file for persistence."""
        history_data = {
            "gwfout_path": self.gwfout_path,
            "channels": self.loaded_channels
        }
        with open(HISTORY_FILE, "w") as f:
            json.dump(history_data, f, indent=4)


class GWOSCApp:
    def __init__(self, master, root):
        self.master = master
        self.root = root  # Needed for scheduling CEF events
        self.browser = None

        # Navigation Bar UI
        self.navbar = tk.Frame(master, bg="gray", height=40)
        self.navbar.pack(fill="x")

        self.back_btn = Button(self.navbar, text="◀", command=self.go_back)
        self.back_btn.pack(side="left")

        self.forward_btn = Button(self.navbar, text="▶", command=self.go_forward)
        self.forward_btn.pack(side="left")

        self.reload_btn = Button(self.navbar, text="🔄", command=self.reload_page)
        self.reload_btn.pack(side="left")

        self.url_entry = Entry(self.navbar, width=50)
        self.url_entry.pack(side="left", fill="x", expand=True)
        self.url_entry.bind("<Return>", self.load_url)

        # Frame for Browser
        self.browser_frame = tk.Frame(master, bg="black")
        self.browser_frame.pack(fill="both", expand=True)

        # Initialize CEF in the UI thread
        self.root.after(100, self.init_cef)
        self.master.bind("<Configure>", self.on_resize)  # Resize handling

        
    def init_cef(self):
        """Initializes CEF and creates the browser."""
        sys.excepthook = cef.ExceptHook  # Catch CEF exceptions
        cef.Initialize()

        # Create browser after the widget is ready
        self.master.after(500, self.create_browser)

        # Start CEF message loop inside Tkinter's event loop
        self.master.after(10, self.cef_loop)

    def create_browser(self):
        """Embeds the browser inside the GWOSCRef tab."""
        window_info = cef.WindowInfo()
        window_info.SetAsChild(self.browser_frame.winfo_id())

        self.browser = cef.CreateBrowserSync(window_info, url="https://gwosc.org/data/")
        self.url_entry.insert(0, "https://gwosc.org/data/")  # Show URL

    def cef_loop(self):
        """Runs CEF's message loop inside Tkinter's event loop."""
        cef.MessageLoopWork()
        self.master.after(10, self.cef_loop)

    def on_resize(self, event=None):
        """Handles resizing the browser when the window changes."""
        if self.browser:
            width = self.browser_frame.winfo_width()
            height = self.browser_frame.winfo_height()
            if width > 0 and height > 0:
                self.browser.SetBounds(0, 0, width, height)

    def go_back(self):
        if self.browser:
            self.browser.GoBack()

    def go_forward(self):
        if self.browser:
            self.browser.GoForward()

    def reload_page(self):
        if self.browser:
            self.browser.Reload()

    def load_url(self, event=None):
        url = self.url_entry.get()
        if self.browser and url:
            self.browser.LoadUrl(url)


class Omiviz:
    def __init__(self, root):
        self.root = root
        self.config_data = {}
        self.ui_elements = {}
        self.plot_files = []  # Store generated plots
        self.current_plot_index = 0  # Track displayed plot

        # Scrollable Frame
        self.canvas = tk.Canvas(root)
        self.scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.window_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Create GUI elements
        self.create_widgets()

    def start_loading(self):
        """Start the loading animation."""
        self.progress.start()

    def stop_loading(self):
        """Stop the loading animation."""
        self.progress.stop()

    def update_progress(self, text):
        """Update progress based on Omicron output."""
        if "Processing" in text or "Generating" in text:
            self.progress.step(10)  # Move progress slightly

    def show_previous_plot(self):
        """Scrolls backward through the plots."""
        if self.current_plot_index > 0:
            self.current_plot_index -= 1
            self.show_plot()
        self.update_navigation_buttons()

    def show_next_plot(self):
        """Scrolls forward through the plots."""
        if self.current_plot_index < len(self.plot_files) - 1:
            self.current_plot_index += 1
            self.show_plot()
        self.update_navigation_buttons()

    def update_navigation_buttons(self):
        """Updates the state of navigation buttons."""
        self.prev_button.config(state=tk.NORMAL if self.current_plot_index > 0 else tk.DISABLED)
        self.next_button.config(state=tk.NORMAL if self.current_plot_index < len(self.plot_files) - 1 else tk.DISABLED)


    def create_widgets(self):
        # File/Folder Selector
        self.create_file_selector("Select Root File(s) or Folder:", "OMICRON FILE", row=1, column=0)

        # Channel Input (Defaults to folder name)
        self.valent("Channel Name:", "OMICRON CHANNEL", row=2, col=0)

        # GPS Start and End Time (Editable)
        self.valent("GPS Start Time:", "OMICRON GPS-START", row=3, col=0)
        self.valent("GPS End Time:", "OMICRON GPS-END", row=4, col=0)
        self.create_output_path_selector("Select Output Folder:", "OMICRON OUTPUT", row=5, column=0)
    
        # Button Frame
        button_frame = tk.Frame(self.scrollable_frame, bd=2, relief="groove", padx=5, pady=5)
        button_frame.grid(row=10, column=0, columnspan=4, pady=10, sticky="ew")
        self.run_button = tk.Button(button_frame, text="Run Omicron Plot", command=self.run_omicron_plot)
        self.run_button.pack(side="left", padx=20)

        # Image Display Frame
        self.image_frame = tk.Frame(self.scrollable_frame)
        self.image_frame.grid(row=11, column=0, columnspan=4, pady=10, sticky="ew")

        self.image_label = tk.Label(self.image_frame, text="No Plot Available", width=50, height=25, bg="gray")
        self.image_label.pack()

        # Navigation Buttons
        nav_frame = tk.Frame(self.scrollable_frame)
        nav_frame.grid(row=12, column=0, columnspan=4, pady=10, sticky="ew")

        self.prev_button = tk.Button(nav_frame, text="⬅ Previous", command=self.show_previous_plot, state=tk.DISABLED)
        self.prev_button.pack(side="left", padx=20)

        self.next_button = tk.Button(nav_frame, text="Next ➡", command=self.show_next_plot, state=tk.DISABLED)
        self.next_button.pack(side="right", padx=20)
        self.progress = ttk.Progressbar(self.scrollable_frame, orient="horizontal", length=300, mode="indeterminate")
        self.progress.grid(row=13, column=0, columnspan=4, pady=10, sticky="ew")

    def valent(self, label, key, frame=None, row=0, col=0, editable=True):
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=col, sticky="w", padx=5, pady=5)
        var = tk.StringVar(value=self.config_data.get(key, ""))
        entry = tk.Entry(target_frame, textvariable=var, width=15, state="normal")  
        entry.grid(row=row, column=col + 1, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = var

    def create_output_path_selector(self, label, key, frame=None, row=0, column=0):
        """Allows selecting an output folder."""
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=column, sticky="w", padx=5, pady=5)

        var = tk.StringVar(value=self.config_data.get(key, ""))
        button = tk.Button(target_frame, text="Browse", command=lambda: self.select_output_folder(var))
        button.grid(row=row, column=2, padx=5, pady=5)

        entry = tk.Entry(target_frame, textvariable=var, width=40, state="readonly")
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = var

    def select_output_folder(self, var):
        """Allows selecting an output folder."""
        folder_path = filedialog.askdirectory()  # Open directory selection dialog
        if folder_path:
            var.set(folder_path)  # Store the selected folder path

    def create_file_selector(self, label, key, frame=None, row=0, column=0):
        """Allows selecting either a single file or a folder containing `.root` files."""
        target_frame = frame if frame else self.scrollable_frame
        tk.Label(target_frame, text=label).grid(row=row, column=column, sticky="w", padx=5, pady=5)

        var = tk.StringVar(value=self.config_data.get(key, ""))
        button = tk.Button(target_frame, text="Browse", command=lambda: self.select_file_or_folder(var))
        button.grid(row=row, column=2, padx=5, pady=5)

        entry = tk.Entry(target_frame, textvariable=var, width=40, state="readonly")
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=5)
        self.ui_elements[key] = var

    def select_file_or_folder(self, var):
        """Allows selecting a folder (grabs all `.root` files) or an individual file."""
        path = filedialog.askdirectory() or filedialog.askopenfilename(filetypes=[("Root Files", "*.root")])

        if os.path.isdir(path):  # If a folder is selected
            root_files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith(".root")]
            if not root_files:
                messagebox.showwarning("Warning", "No .root files found in selected folder.")
                return
            var.set(path)  # Store folder path
            # Auto-set channel name based on folder name
            folder_name = os.path.basename(path).replace("", ":")
            self.ui_elements["OMICRON CHANNEL"].set(folder_name)
            #print("folder name ", folder_name)

            # Convert all root file paths to WSL format
            root_files_wsl = []
            for f in root_files:
                abs_path = os.path.abspath(f)  # Get the absolute path
                norm_path = os.path.normpath(abs_path)  # Normalize path to handle slashes properly
                wsl_path = "/mnt/c/" + norm_path.replace("\\", "/")[2:]  # Convert backslashes to slashes and remove "C:" part
                root_files_wsl.append(wsl_path)
            #print("Converted root files:", root_files_wsl)

        elif path:  # If a single file is selected
            var.set(path)
            # Auto-set channel name based on file's parent folder
            folder_name = os.path.basename(os.path.dirname(path)).replace("_", ":")
            self.ui_elements["OMICRON CHANNEL"].set(folder_name)

            # Convert the single file path to WSL format
            abs_path = os.path.abspath(path)  # Get the absolute path
            norm_path = os.path.normpath(abs_path)  # Normalize path to handle slashes properly
            path_wsl = "/mnt/c/" + norm_path.replace("\\", "/")[2:]  # Convert backslashes to slashes and remove "C:" part
            #print("Converted file path:", path_wsl)

            return path_wsl  # Return the WSL-formatted path for use in further commands

    def run_omicron_plot(self):
        selected_path = self.ui_elements["OMICRON FILE"].get()
        gps_start = self.ui_elements["OMICRON GPS-START"].get()
        gps_end = self.ui_elements["OMICRON GPS-END"].get()
        channel_name = self.ui_elements["OMICRON CHANNEL"].get()
        output_folder = self.ui_elements["OMICRON OUTPUT"].get()  # Get the output folder

        if not selected_path or not gps_start or not gps_end or not channel_name:
            messagebox.showerror("Error", "Please fill in all fields!")
            return

        # Convert selected path to WSL format
        if os.path.isdir(selected_path):
            root_files = []
            for f in os.listdir(selected_path):
                if f.endswith(".root"):
                    abs_path = os.path.abspath(os.path.join(selected_path, f))  # Get the absolute path
                    norm_path = os.path.normpath(abs_path)  # Normalize path to handle slashes properly
                    wsl_path = "/mnt/c/" + norm_path.replace("\\", "/")[2:]  # Convert backslashes to slashes and remove "C:" part
                    root_files.append(wsl_path)
            input_files = " ".join(root_files)

            #print("Converted root files:", root_files)
            input_files = " ".join(root_files)

            #print("Converted root files:", root_files)

        else:
            # Convert the single file to WSL format
            abs_path = os.path.abspath(selected_path)  # Get the absolute path
            norm_path = os.path.normpath(abs_path)  # Normalize path to handle slashes properly
            input_files = "/mnt/c/" + norm_path.replace("\\", "/")[2:]  # Convert backslashes to slashes and remove "C:" part
            #print("Converted file path:", input_files)

        # output_folder_name = f"{channel_name}_{gps_start}_{gps_end}".replace(":", "_")
        # #print("*****************",channel_name)
        # output_folder_path = os.path.join(os.getcwd(), output_folder_name)

        # os.makedirs(output_folder_path, exist_ok=True)
        # abs_path = os.path.abspath(output_folder_path).replace("\\", "/")
        # drive_letter = abs_path[0].lower()
        # path_without_drive = abs_path[3:]
        # self.wsl_project_dir = f"/mnt/{drive_letter}/{path_without_drive}"

        # #print(f"WSL Project Directory: {self.wsl_project_dir}")

        #print("++++++++++",input_files,"++++++++++++++")
        # Construct the command to run omicron-plot4
        print(output_folder)
        self.wsl_project_dir = output_folder
        output_fil = "/mnt/c/" + output_folder.replace("\\", "/")[2:]  # Convert backslashes to slashes and remove "C:" part
        output_fil = output_fil.replace("//", "/")
        print(output_fil)
        output_folder = output_fil
        command = [
            "export C_INCLUDE_PATH=/usr/include",
            "export CPLUS_INCLUDE_PATH=/usr/include", 
            f"omicron-plot file={input_files} gps-start={gps_start} gps-end={gps_end} outformat=png outdir={output_fil}" 
        ]
        # Use threading to run the command in the background
        threading.Thread(target=self.execute_command, args=(command, gps_start, gps_end, self.wsl_project_dir), daemon=True).start()

    def execute_command(self, command, gps_start, gps_end, output_folder):
        """Runs the Omicron plot command inside a full WSL shell session with logging."""
        try:
            for cmd in command:
                log_message = f"Executing WSL Command: {cmd}"
                logging.info(log_message)
                #print(log_message)  # Debug Output

                # Start loading animation
                self.start_loading()

                # Run full WSL session and execute command
                wsl_command = f"wsl bash -ic '{cmd}'"
                process = subprocess.Popen(wsl_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
                for line in process.stdout:
                    logging.info(line.strip())  # Log output
                   # print(line.strip())  # Console output
                    self.update_progress(line.strip())  # Update progress bar

                for line in process.stderr:
                    logging.error(line.strip())  # Log errors
                   # print("ERROR:", line.strip())

                # Stop loading and load plots
                self.stop_loading()
                self.load_plots(output_folder)
                logging.info("Omicron plot execution completed successfully.")

        except Exception as e:
            error_message = f"Execution failed: {e}"
            logging.error(error_message)
            #print(error_message)
            self.stop_loading()


    def show_plot(self):
        """Displays the current plot in the GUI."""
        if not self.plot_files:
            self.image_label.config(text="No plots available", image="", bg="gray")
            return

        try:
            # Ensure current_plot_index is within bounds
            if 0 <= self.current_plot_index < len(self.plot_files):
                image_path = self.plot_files[self.current_plot_index]
                logging.info(f"Displaying plot: {image_path}")  # Log the displayed plot

                image = Image.open(image_path)

                # Set the size of the image label based on the size of the image
                image_width, image_height = image.size

                # Set max width and height based on available space
                max_width = 600  # You can adjust this value
                max_height = 300  # You can adjust this value

                # Resize the image to fit within the available space
                if image_width > max_width or image_height > max_height:
                    image = image.resize((max_width, int(max_width * image_height / image_width)), Image.LANCZOS)

                self.photo = ImageTk.PhotoImage(image)  # Store reference to prevent garbage collection

                # Resize the image_label widget to match the image size
                self.image_label.config(image=self.photo, text="", bg="white", width=max_width, height=max_height)
                self.image_label.image = self.photo  # Explicitly store the image reference

            else:
                logging.error(f"Invalid plot index: {self.current_plot_index}")
                self.image_label.config(text="Invalid plot index", bg="red")

        except Exception as e:
            logging.error(f"Error displaying plot: {e}")
            self.image_label.config(text="Error loading plot", bg="red")

    def load_plots(self, folder):
        """Loads the plots from WSL and updates the GUI."""
        try:
            if not os.path.exists(folder):
                raise FileNotFoundError(f"The folder {folder} does not exist.")
            
            self.plot_files = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".png")])
            
            if self.plot_files:
                self.current_plot_index = 0
                self.show_plot()
                self.update_navigation_buttons()
            else:
                logging.warning("No PNG files found in the folder.")
                messagebox.showwarning("Warning", "No plots found. Check if Omicron-plot executed correctly.")
                
        except FileNotFoundError as e:
            logging.error(f"Folder not found: {e}")
            messagebox.showerror("Error", f"Folder not found: {e}")
        except Exception as e:
            logging.error(f"Failed to load plots: {e}")
            messagebox.showerror("Error", f"Failed to load plots: {e}")

###############################################################################Time Series Waveforms#############################################################


class TimeSrswaveform:
    def __init__(self, root):
        self.root = root
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Canvas for scrolling
        self.canvas = tk.Canvas(root)
        self.scroll_y = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(root, orient="horizontal", command=self.canvas.xview)
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")

        self.frame = ttk.Frame(self.canvas)
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")  


        # Main Input Frame
        input_frame = ttk.LabelFrame(self.frame, text="Input Parameters")
        input_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Catalog Selection
        ttk.Label(input_frame, text="Catalog:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.catalog_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.catalog_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.catalog_dropdown.bind("<<ComboboxSelected>>", self.fetch_events)

        # Event Selection
        ttk.Label(input_frame, text="Event:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.event_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.event_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.event_dropdown.bind("<<ComboboxSelected>>",self.fetch_event_details)

        # Run Selection
        ttk.Label(input_frame, text="Run:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.run_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.run_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Detector Selection
        ttk.Label(input_frame, text="Detector:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.detector_dropdown = tk.Listbox(input_frame, selectmode="multiple", height=3)
        for det in ["L1", "H1", "V1"]:
            self.detector_dropdown.insert(tk.END, det)
        self.detector_dropdown.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        self.detector_dropdown.bind("<<ComboboxSelected>>",self.update_urls)

        # GPS Time Inputs
        ttk.Label(input_frame, text="Start Time:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.gps_start_entry = ttk.Entry(input_frame, width=20)
        self.gps_start_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="End Time (Optional):").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.gps_end_entry = ttk.Entry(input_frame, width=20)
        self.gps_end_entry.grid(row=0, column=5, padx=5, pady=5, sticky="ew")

        # GPS ⇄ UTC Converter
        self.mode = tk.StringVar(value="gps_to_utc")
        conversion_frame = ttk.LabelFrame(self.frame, text="GPS ⇄ UTC Converter")
        conversion_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        self.convert_entry = ttk.Entry(conversion_frame, width=20)
        self.convert_entry.grid(row=0, column=0, padx=5, pady=5)

        self.convert_button = ttk.Button(conversion_frame, text="Convert", command=self.convert_time)
        self.convert_button.grid(row=0, column=1, padx=5, pady=5)

        self.result_label = ttk.Label(conversion_frame, text="Result: ")
        self.result_label.grid(row=0, column=2, padx=5, pady=5)

        self.toggle_button = ttk.Button(conversion_frame, text="Switch to UTC → GPS", command=self.toggle_mode)
        self.toggle_button.grid(row=0, column=3, padx=5, pady=5)

        # Event URLs Frame
        url_frame = ttk.LabelFrame(self.frame, text="Event URLs")
        url_frame.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        self.url_dropdown = ttk.Combobox(url_frame, state="readonly")
        self.url_dropdown.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.copy_button = ttk.Button(url_frame, text="Copy URL", command=self.copy_url)
        self.copy_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Save Parameters Button
        self.save_button = ttk.Button(input_frame, text="Save Parameters", command=self.save_params)
        self.save_button.grid(row=2, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        self.plot_frame = ttk.Frame(self.frame)
        self.plot_frame.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")

        self.prefetch_data()
        self.plot_button = tk.Button(root, text="Plot TimeSeries", command=lambda: self.plot_gw_event(self.catalog_dropdown.get(),[self.detector_dropdown.get(idx) for idx in self.detector_dropdown.curselection()],float(self.gps_start_entry.get()),float(self.gps_end_entry.get())))
        self.plot_button.grid(row=0, column=3, columnspan=2, pady=10)


    def copy_url(self):
        selected_url = self.url_dropdown.get()
        if selected_url:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_url)
            self.root.update()  # Keep clipboard data even after the app closes
            messagebox.showinfo("Copied", "URL copied to clipboard!")
        else:
            messagebox.showwarning("Warning", "No URL selected!")

    # 🔹 Prefetch Catalogs & Runs at Startup
    def prefetch_data(self):
        try:
            catalogs = find_datasets(type="catalog")
            self.catalog_dropdown["values"] = catalogs
            if catalogs:
                self.catalog_dropdown.current(0)

            runs = find_datasets(type="run")
            self.run_dropdown["values"] = runs
            if runs:
                self.run_dropdown.current(0)

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching catalogs/runs: {e}")

    # 🔹 Fetch Events Based on Selected Catalog
    def fetch_events(self, event=None):
        selected_catalog = self.catalog_dropdown.get()
        if not selected_catalog:
            return

        try:
            events = datasets.find_datasets(type="events", catalog=selected_catalog)
            self.event_dropdown["values"] = events
            if events:
                self.event_dropdown.current(0)
                self.fetch_event_details()  # Auto-update details for first event

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching events: {e}")

    # 🔹 Fetch Event GPS & URLs
    def fetch_event_details(self, event=None):
        selected_event = self.event_dropdown.get()
        if not selected_event:
            return
        try:
            gps_time = event_gps(selected_event)
            self.gps_start_entry.delete(0, tk.END)
            self.gps_start_entry.insert(0, str(gps_time))

            self.update_urls()

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching event details: {e}")

    # 🔹 Update URLs Based on Event & Detector
    def update_urls(self, event=None):
        selected_event = self.event_dropdown.get()
        selected_detectors = [self.detector_dropdown.get(idx) for idx in self.detector_dropdown.curselection()]
        if not selected_event or not selected_detectors:
            return

        try:
            urls = get_event_urls(selected_event)
            filtered_urls = [url for url in urls if any(det in url for det in selected_detectors)]
            self.url_dropdown["values"] = filtered_urls
            if filtered_urls:
                self.url_dropdown.current(0)

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching event URLs: {e}")

    # 🔹 Toggle GPS ⇄ UTC Mode
    def toggle_mode(self):
        if self.mode.get() == "gps_to_utc":
            self.mode.set("utc_to_gps")
            self.toggle_button.config(text="Switch to GPS → UTC")
        else:
            self.mode.set("gps_to_utc")
            self.toggle_button.config(text="Switch to UTC → GPS")

    # 🔹 Convert GPS ⇄ UTC
    def convert_time(self):
        time_input = self.convert_entry.get().strip()
        if not time_input:
            messagebox.showerror("Error", "Please enter a valid time!")
            return

        try:
            if self.mode.get() == "gps_to_utc":
                gps_time = float(time_input)
                utc_time = gp_time.from_gps(int(gps_time))
                self.result_label.config(text=f"UTC Time: {utc_time}")
            else:
                utc_time = datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
                gps_time = gp_time.to_gps(utc_time)
                self.result_label.config(text=f"GPS Time: {gps_time}")

        except Exception as e:
            messagebox.showerror("Error", f"Conversion failed: {e}")
 

    def save_params(self):
        """Overwrite 'gwfparams.csv' with the latest input values, including headers."""
        file_path = "gwfparams.csv"

        # Define column headers
        headers = ["Catalog", "Event", "Run", "Detector(s)", "Start Time (GPS)", "End Time (GPS)", "Event URL"]

        # Collect values
        selected_detectors = ", ".join([self.detector_dropdown.get(idx) for idx in self.detector_dropdown.curselection()])
        params = [
            self.catalog_dropdown.get(),
            self.event_dropdown.get(),
            self.run_dropdown.get(),
            selected_detectors,  # Updated for multiple detectors
            self.gps_start_entry.get(),
            self.gps_end_entry.get(),
            self.url_dropdown.get(),  # Assuming this holds the event URL
        ]

        try:
            with open(file_path, mode="w", newline="") as file:  # "w" mode overwrites the file
                writer = csv.writer(file)
                writer.writerow(headers)  # Always write headers
                writer.writerow(params)   # Write only the latest values

            messagebox.showinfo("Success", f"Parameters saved to {file_path}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save parameters: {e}")

    def plot_gw_event(self, event_name, detectors, gps_start, gps_end):
        """Plot gravitational wave event data for multiple detectors."""

        # Generate the figure and axes
        fig, ax = plt.subplots(figsize=(8, 5))
        colors = ['b', 'r', 'g']  # Blue, Red, Green for H1, L1, V1

        for i, det in enumerate(detectors):
            try:
                # Fetch GWOSC data for each detector
                data = TimeSeries.fetch_open_data(det, gps_start, gps_end, verbose=True)

                # Plot with different colors
                ax.plot(data.times, data, label=f"{det} - {event_name}", color=colors[i % len(colors)])

            except Exception as e:
                print(f"Error fetching data for {det}: {e}")

        # Labels and grid
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Strain")
        ax.set_title(f"Gravitational Wave Event: {event_name}")
        ax.legend()
        ax.grid(True)

        # Improve layout
        plt.tight_layout()

        # Embed plot in Tkinter
        canvas = FigureCanvasTkAgg(fig, master=self.root)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.grid(row=2, column=0, columnspan=4, sticky="nsew")
        canvas.draw()

        # Add Matplotlib toolbar
        toolbar_fft = NavigationToolbar2Tk(canvas, self.root)
        toolbar_fft.grid(row=3, column=0, columnspan=1, pady=5)

        # Save Button
        def save_plot():
            file_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png"), ("All Files", "*.*")])
            if file_path:
                fig.savefig(file_path)
                print(f"Plot saved as {file_path}")

        # Configure grid for resizing
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        
########################################################################################################################################################################
#########################################################################################################FFT############################################################
class FFT:
    def __init__(self, root):
        self.root = root
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Canvas for scrolling
        self.canvas = tk.Canvas(root)
        self.scroll_y = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(root, orient="horizontal", command=self.canvas.xview)
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")

        self.frame = ttk.Frame(self.canvas)
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")  


        # Main Input Frame
        input_frame = ttk.LabelFrame(self.frame, text="Input Parameters")
        input_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Catalog Selection
        ttk.Label(input_frame, text="Catalog:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.catalog_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.catalog_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.catalog_dropdown.bind("<<ComboboxSelected>>", self.fetch_events)

        # Event Selection
        ttk.Label(input_frame, text="Event:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.event_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.event_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.event_dropdown.bind("<<ComboboxSelected>>",self.fetch_event_details)

        # Run Selection
        ttk.Label(input_frame, text="Run:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.run_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.run_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Detector Selection
        ttk.Label(input_frame, text="Detector:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.detector_listbox = tk.Listbox(input_frame, selectmode="multiple", exportselection=False, height=3)
        for detector in ["L1", "H1", "V1"]:
            self.detector_listbox.insert(tk.END, detector)
        self.detector_listbox.grid(row=1, column=3, padx=5, pady=5, sticky="ew")


        # GPS Time Inputs
        ttk.Label(input_frame, text="Start Time:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.gps_start_entry = ttk.Entry(input_frame, width=20)
        self.gps_start_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="End Time (Optional):").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.gps_end_entry = ttk.Entry(input_frame, width=20)
        self.gps_end_entry.grid(row=0, column=5, padx=5, pady=5, sticky="ew")

        # GPS ⇄ UTC Converter
        self.mode = tk.StringVar(value="gps_to_utc")
        conversion_frame = ttk.LabelFrame(self.frame, text="GPS ⇄ UTC Converter")
        conversion_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        self.convert_entry = ttk.Entry(conversion_frame, width=20)
        self.convert_entry.grid(row=0, column=0, padx=5, pady=5)

        self.convert_button = ttk.Button(conversion_frame, text="Convert", command=self.convert_time)
        self.convert_button.grid(row=0, column=1, padx=5, pady=5)

        self.result_label = ttk.Label(conversion_frame, text="Result: ")
        self.result_label.grid(row=0, column=2, padx=5, pady=5)

        self.toggle_button = ttk.Button(conversion_frame, text="Switch to UTC → GPS", command=self.toggle_mode)
        self.toggle_button.grid(row=0, column=3, padx=5, pady=5)

        # Event URLs Frame
        url_frame = ttk.LabelFrame(self.frame, text="Event URLs")
        url_frame.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        self.url_dropdown = ttk.Combobox(url_frame, state="readonly")
        self.url_dropdown.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.copy_button = ttk.Button(url_frame, text="Copy URL", command=self.copy_url)
        self.copy_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Save Parameters Button
        self.save_button = ttk.Button(input_frame, text="Save Parameters", command=self.save_params)
        self.save_button.grid(row=2, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        self.plot_frame = ttk.Frame(self.frame)
        self.plot_frame.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")
        self.prefetch_data()
        self.fft_button = tk.Button(root, text="Run FFT", command=lambda: self.fft(
        self.catalog_dropdown.get(),[self.detector_listbox.get(i) for i in self.detector_listbox.curselection()],float(self.gps_start_entry.get()),float(self.gps_end_entry.get())))
        self.fft_button.grid(row=4, column=3, columnspan=2, pady=10)

    def copy_url(self):
        selected_url = self.url_dropdown.get()
        if selected_url:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_url)
            self.root.update()  # Keep clipboard data even after the app closes
            messagebox.showinfo("Copied", "URL copied to clipboard!")
        else:
            messagebox.showwarning("Warning", "No URL selected!")

    # 🔹 Prefetch Catalogs & Runs at Startup
    def prefetch_data(self):
        try:
            catalogs = find_datasets(type="catalog")
            self.catalog_dropdown["values"] = catalogs
            if catalogs:
                self.catalog_dropdown.current(0)

            runs = find_datasets(type="run")
            self.run_dropdown["values"] = runs
            if runs:
                self.run_dropdown.current(0)

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching catalogs/runs: {e}")

    # 🔹 Fetch Events Based on Selected Catalog
    def fetch_events(self, event=None):
        selected_catalog = self.catalog_dropdown.get()
        if not selected_catalog:
            return

        try:
            events = datasets.find_datasets(type="events", catalog=selected_catalog)
            self.event_dropdown["values"] = events
            if events:
                self.event_dropdown.current(0)
                self.fetch_event_details()  # Auto-update details for first event

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching events: {e}")

    # 🔹 Fetch Event GPS & URLs
    def fetch_event_details(self, event=None):
        selected_event = self.event_dropdown.get()
        if not selected_event:
            return
        try:
            gps_time = event_gps(selected_event)
            self.gps_start_entry.delete(0, tk.END)
            self.gps_start_entry.insert(0, str(gps_time))

            self.update_urls()

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching event details: {e}")

    # 🔹 Update URLs Based on Event & Detector
    def update_urls(self, event=None):
        selected_event = self.event_dropdown.get()
        selected_detectors = [self.detector_listbox.get(i) for i in self.detector_listbox.curselection()]
        if not selected_event or not selected_detectors:
            return
        try:
            urls = get_event_urls(selected_event)
            filtered_urls = [url for url in urls if any(det in url for det in selected_detectors)]
            self.url_dropdown["values"] = filtered_urls
            if filtered_urls:
                self.url_dropdown.current(0)
        except Exception as e:
            messagebox.showerror("Error", f"Error fetching event URLs: {e}")

    # 🔹 Toggle GPS ⇄ UTC Mode
    def toggle_mode(self):
        if self.mode.get() == "gps_to_utc":
            self.mode.set("utc_to_gps")
            self.toggle_button.config(text="Switch to GPS → UTC")
        else:
            self.mode.set("gps_to_utc")
            self.toggle_button.config(text="Switch to UTC → GPS")

    # 🔹 Convert GPS ⇄ UTC
    def convert_time(self):
        time_input = self.convert_entry.get().strip()
        if not time_input:
            messagebox.showerror("Error", "Please enter a valid time!")
            return

        try:
            if self.mode.get() == "gps_to_utc":
                gps_time = float(time_input)
                utc_time = gp_time.from_gps(int(gps_time))
                self.result_label.config(text=f"UTC Time: {utc_time}")
            else:
                utc_time = datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
                gps_time = gp_time.to_gps(utc_time)
                self.result_label.config(text=f"GPS Time: {gps_time}")

        except Exception as e:
            messagebox.showerror("Error", f"Conversion failed: {e}")
 

    def save_params(self):
        """Overwrite 'gwfparams.csv' with the latest input values, including headers."""
        file_path = "gwfparams.csv"

        # Define column headers
        headers = ["Catalog", "Event", "Run", "Detector", "Start Time (GPS)", "End Time (GPS)", "Event URL"]

        # Collect values
        params = [
            self.catalog_dropdown.get(),
            self.event_dropdown.get(),
            self.run_dropdown.get(),
            ", ".join([self.detector_listbox.get(i) for i in self.detector_listbox.curselection()]),
            self.gps_start_entry.get(),
            self.gps_end_entry.get(),
            self.url_dropdown.get(),  # Assuming this holds the event URL
        ]

        try:
            with open(file_path, mode="w", newline="") as file:  # "w" mode overwrites the file
                writer = csv.writer(file)
                writer.writerow(headers)  # Always write headers
                writer.writerow(params)   # Write only the latest values

            messagebox.showinfo("Success", f"Parameters saved to {file_path}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save parameters: {e}")


    def fft(self, event_name, detectors, gps_start, gps_end):
        fig_fft, ax_fft = plt.subplots(figsize=(8, 5))
        data_dict = {}  # Dictionary to store TimeSeries data for each selected detector
        for detector in detectors:  # Loop through selected detectors
            if detector == "L1":
                var_name = "ldata"
            elif detector == "H1":
                var_name = "hdata"
            elif detector == "V1":
                var_name = "vdata"
            else:
                var_name = f"{detector.lower()}data"  # Fallback for unexpected detectors
            data_dict[var_name] = TimeSeries.fetch_open_data(detector, gps_start, gps_end, verbose=True)
            window = get_window('hann', data_dict[var_name].size)
            win_data = data_dict[var_name] * window  
            fftamp = win_data.fft().abs()
            ax_fft.plot(fftamp.frequencies.value, fftamp, label=f"FFT Amplitude ({detector})")
        ax_fft.set_xlabel("Frequency (Hz)")
        ax_fft.set_ylabel("Amplitude")
        ax_fft.set_xscale("log")
        ax_fft.set_yscale("log")
        ax_fft.set_title(f"FFT of {event_name}")
        ax_fft.legend()
        ax_fft.grid(True)
        canvas_fft = FigureCanvasTkAgg(fig_fft, master=self.root)
        canvas_fft_widget = canvas_fft.get_tk_widget()
        canvas_fft_widget.grid(row=3, column=0, columnspan=1, sticky="nsew")
        canvas_fft.draw()
        toolbar_fft = NavigationToolbar2Tk(canvas_fft, self.root)
        toolbar_fft.grid(row=5, column=0, columnspan=1, pady=5)

        # Save Button
        def save_plot():
            file_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png"), ("All Files", "*.*")])
            if file_path:
                fig_fft.savefig(file_path)  # Use fig_fft instead of fig
                print(f"Plot saved as {file_path}")

        save_button = tk.Button(self.root, text="Save FFT Plot", command=save_plot)
        save_button.grid(row=4, column=1, columnspan=2, pady=10)

        # Configure grid for resizing
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
########################################################################################################################################################################
#########################################################################################PSDs############################################################################

class PSDs:
    def __init__(self, root):
        self.root = root
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Canvas for scrolling
        self.canvas = tk.Canvas(root)
        self.scroll_y = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(root, orient="horizontal", command=self.canvas.xview)
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")

        self.frame = ttk.Frame(self.canvas)
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")  


        # Main Input Frame
        input_frame = ttk.LabelFrame(self.frame, text="Input Parameters")
        input_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Catalog Selection
        ttk.Label(input_frame, text="Catalog:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.catalog_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.catalog_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.catalog_dropdown.bind("<<ComboboxSelected>>", self.fetch_events)

        # Event Selection
        ttk.Label(input_frame, text="Event:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.event_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.event_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.event_dropdown.bind("<<ComboboxSelected>>",self.fetch_event_details)

        # Run Selection
        ttk.Label(input_frame, text="Run:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.run_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.run_dropdown.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        # Detector Selection
        ttk.Label(input_frame, text="Detector:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.detector_dropdown = tk.Listbox(input_frame, selectmode="multiple", height=3)
        for det in ["L1", "H1", "V1"]:
            self.detector_dropdown.insert(tk.END, det)
        self.detector_dropdown.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        self.detector_dropdown.bind("<<ComboboxSelected>>",self.update_urls)

        # GPS Time Inputs
        ttk.Label(input_frame, text="Start Time:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.gps_start_entry = ttk.Entry(input_frame, width=20)
        self.gps_start_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="End Time (Optional):").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.gps_end_entry = ttk.Entry(input_frame, width=20)
        self.gps_end_entry.grid(row=0, column=5, padx=5, pady=5, sticky="ew")
        # FFT & Method Inputs
        ttk.Label(input_frame, text="FFT Length:").grid(row=1, column=4, padx=5, pady=5, sticky="w")
        self.fft_length_entry = ttk.Entry(input_frame, width=10)
        self.fft_length_entry.grid(row=1, column=5, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="Method:").grid(row=1, column=6, padx=5, pady=5, sticky="w")
        self.method_entry = ttk.Combobox(input_frame, width=10, values=["median", "welch"], state="readonly")
        self.method_entry.grid(row=1, column=7, padx=5, pady=5, sticky="ew")
        self.method_entry.current(0)  # Default selection to "median"
        # GPS ⇄ UTC Converter
        self.mode = tk.StringVar(value="gps_to_utc")
        conversion_frame = ttk.LabelFrame(self.frame, text="GPS ⇄ UTC Converter")
        conversion_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        self.convert_entry = ttk.Entry(conversion_frame, width=20)
        self.convert_entry.grid(row=0, column=0, padx=5, pady=5)

        self.convert_button = ttk.Button(conversion_frame, text="Convert", command=self.convert_time)
        self.convert_button.grid(row=0, column=1, padx=5, pady=5)

        self.result_label = ttk.Label(conversion_frame, text="Result: ")
        self.result_label.grid(row=0, column=2, padx=5, pady=5)

        self.toggle_button = ttk.Button(conversion_frame, text="Switch to UTC → GPS", command=self.toggle_mode)
        self.toggle_button.grid(row=0, column=3, padx=5, pady=5)

        # Event URLs Frame
        url_frame = ttk.LabelFrame(self.frame, text="Event URLs")
        url_frame.grid(row=1, column=1, padx=5, pady=5, sticky="nsew")

        self.url_dropdown = ttk.Combobox(url_frame, state="readonly")
        self.url_dropdown.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self.copy_button = ttk.Button(url_frame, text="Copy URL", command=self.copy_url)
        self.copy_button.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        # Save Parameters Button
        self.save_button = ttk.Button(input_frame, text="Save Parameters", command=self.save_params)
        self.save_button.grid(row=2, column=0, columnspan=2, padx=5, pady=10, sticky="ew")
        self.plot_frame = ttk.Frame(self.frame)
        self.plot_frame.grid(row=3, column=0, padx=5, pady=5, sticky="nsew")

        self.prefetch_data()
        self.plot_button = tk.Button(root, text="Plot TimeSeries", command=lambda: self.psds(self.catalog_dropdown.get(),[self.detector_dropdown.get(idx) for idx in self.detector_dropdown.curselection()],float(self.gps_start_entry.get()),float(self.gps_end_entry.get()),int(self.fft_length_entry.get()),self.method_entry.get()))
        self.plot_button.grid(row=0, column=3, columnspan=2, pady=10)


    def copy_url(self):
        selected_url = self.url_dropdown.get()
        if selected_url:
            self.root.clipboard_clear()
            self.root.clipboard_append(selected_url)
            self.root.update()  # Keep clipboard data even after the app closes
            messagebox.showinfo("Copied", "URL copied to clipboard!")
        else:
            messagebox.showwarning("Warning", "No URL selected!")

    # 🔹 Prefetch Catalogs & Runs at Startup
    def prefetch_data(self):
        try:
            catalogs = find_datasets(type="catalog")
            self.catalog_dropdown["values"] = catalogs
            if catalogs:
                self.catalog_dropdown.current(0)

            runs = find_datasets(type="run")
            self.run_dropdown["values"] = runs
            if runs:
                self.run_dropdown.current(0)

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching catalogs/runs: {e}")

    # 🔹 Fetch Events Based on Selected Catalog
    def fetch_events(self, event=None):
        selected_catalog = self.catalog_dropdown.get()
        if not selected_catalog:
            return

        try:
            events = datasets.find_datasets(type="events", catalog=selected_catalog)
            self.event_dropdown["values"] = events
            if events:
                self.event_dropdown.current(0)
                self.fetch_event_details()  # Auto-update details for first event

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching events: {e}")

    # 🔹 Fetch Event GPS & URLs
    def fetch_event_details(self, event=None):
        selected_event = self.event_dropdown.get()
        if not selected_event:
            return
        try:
            gps_time = event_gps(selected_event)
            self.gps_start_entry.delete(0, tk.END)
            self.gps_start_entry.insert(0, str(gps_time))

            self.update_urls()

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching event details: {e}")

    # 🔹 Update URLs Based on Event & Detector
    def update_urls(self, event=None):
        selected_event = self.event_dropdown.get()
        selected_detectors = [self.detector_dropdown.get(idx) for idx in self.detector_dropdown.curselection()]
        if not selected_event or not selected_detectors:
            return

        try:
            urls = get_event_urls(selected_event)
            filtered_urls = [url for url in urls if any(det in url for det in selected_detectors)]
            self.url_dropdown["values"] = filtered_urls
            if filtered_urls:
                self.url_dropdown.current(0)

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching event URLs: {e}")

    # 🔹 Toggle GPS ⇄ UTC Mode
    def toggle_mode(self):
        if self.mode.get() == "gps_to_utc":
            self.mode.set("utc_to_gps")
            self.toggle_button.config(text="Switch to GPS → UTC")
        else:
            self.mode.set("gps_to_utc")
            self.toggle_button.config(text="Switch to UTC → GPS")

    # 🔹 Convert GPS ⇄ UTC
    def convert_time(self):
        time_input = self.convert_entry.get().strip()
        if not time_input:
            messagebox.showerror("Error", "Please enter a valid time!")
            return

        try:
            if self.mode.get() == "gps_to_utc":
                gps_time = float(time_input)
                utc_time = gp_time.from_gps(int(gps_time))
                self.result_label.config(text=f"UTC Time: {utc_time}")
            else:
                utc_time = datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
                gps_time = gp_time.to_gps(utc_time)
                self.result_label.config(text=f"GPS Time: {gps_time}")

        except Exception as e:
            messagebox.showerror("Error", f"Conversion failed: {e}")
 

    def save_params(self):
        """Overwrite 'gwfparams.csv' with the latest input values, including headers."""
        file_path = "gwfparams.csv"

        # Define column headers
        headers = ["Catalog", "Event", "Run", "Detector(s)", "Start Time (GPS)", "End Time (GPS)", "Event URL"]

        # Collect values
        selected_detectors = ", ".join([self.detector_dropdown.get(idx) for idx in self.detector_dropdown.curselection()])
        params = [
            self.catalog_dropdown.get(),
            self.event_dropdown.get(),
            self.run_dropdown.get(),
            selected_detectors,  # Updated for multiple detectors
            self.gps_start_entry.get(),
            self.gps_end_entry.get(),
            self.url_dropdown.get(),  # Assuming this holds the event URL
        ]

        try:
            with open(file_path, mode="w", newline="") as file:  # "w" mode overwrites the file
                writer = csv.writer(file)
                writer.writerow(headers)  # Always write headers
                writer.writerow(params)   # Write only the latest values

            messagebox.showinfo("Success", f"Parameters saved to {file_path}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save parameters: {e}")

    def psds(self, event_name, detectors, gps_start, gps_end, fftlengths, methods):
        """
        Plot Power Spectral Densities (PSDs) for multiple detectors in Tkinter.

        Parameters:
        - event_name: Name of the gravitational wave event
        - detectors: List of detector names (e.g., ['H1', 'L1', 'V1'])
        - gps_start: GPS start time
        - gps_end: GPS end time
        - fftlengths: List of FFT lengths (same length as detectors)
        - methods: List of ASD computation methods (same length as detectors)
        """

        fig, ax = plt.subplots(figsize=(8, 5))
        colors = ['b', 'r', 'g', 'm', 'c', 'y']  # More colors for multiple detectors

        for i, det in enumerate(detectors):
            try:
                # Fetch GWOSC data
                print(i,det)
                data = TimeSeries.fetch_open_data(det, gps_start, gps_end, verbose=True)
                print(data)
                # Get user-specified FFT length and method
                fft_len = fftlengths
                method = methods
                # Compute ASD
                asd = data.asd(fftlength=fft_len, method=method)
                print(asd)
                freqs = asd.frequencies.value
                asd_values = asd.value

                # Plot ASD manually using `ax.plot()`
                ax.plot(freqs, asd_values, color=colors[i % len(colors)], 
                    label=f"{det} - {method.capitalize()} FFT={fft_len}")
            except Exception as e:
                print(f"Error fetching data for {det}: {e}")

        # Set plot labels and limits
        ax.set_xlabel("Frequency [Hz]")
        ax.set_ylabel("ASD [strain/$\sqrt{Hz}$]")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(10, 1400)
        ax.set_ylim(1e-24, 1e-20)
        ax.grid(True, which="both", linestyle="--", alpha=0.5)
        ax.legend()

        plt.title(f"ASD for {event_name}")
        
        # Embed plot in Tkinter
        canvas = FigureCanvasTkAgg(fig, master=self.root)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.grid(row=2, column=0, columnspan=4, sticky="nsew")
        canvas.draw()

        # Add Matplotlib toolbar
        toolbar_fft = NavigationToolbar2Tk(canvas, self.root)
        toolbar_fft.grid(row=3, column=0, columnspan=1, pady=5)

        # Save Button
        def save_plot():
            file_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png"), ("All Files", "*.*")])
            if file_path:
                fig.savefig(file_path)
                print(f"Plot saved as {file_path}")

        save_button = tk.Button(self.root, text="Save Plot", command=save_plot)
        save_button.grid(row=3, column=1, pady=5)

        # Configure grid for resizing
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

########################################################################################################################################################################
########################################################################################################################################################################

class Spectrogram:
    def __init__(self, root):
        self.root = root
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Canvas for scrolling
        self.canvas = tk.Canvas(root)
        self.scroll_y = ttk.Scrollbar(root, orient="vertical", command=self.canvas.yview)
        self.scroll_x = ttk.Scrollbar(root, orient="horizontal", command=self.canvas.xview)
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")

        self.frame = ttk.Frame(self.canvas)
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")  


        # Main Input Frame
        input_frame = ttk.LabelFrame(self.frame, text="Input Parameters")
        input_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Catalog Selection
        ttk.Label(input_frame, text="Catalog:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.catalog_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.catalog_dropdown.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.catalog_dropdown.bind("<<ComboboxSelected>>", self.fetch_events)

        # Event Selection
        ttk.Label(input_frame, text="Event:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.event_dropdown = ttk.Combobox(input_frame, state="readonly")
        self.event_dropdown.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.event_dropdown.bind("<<ComboboxSelected>>",self.fetch_event_details)

        # Detector Selection
        ttk.Label(input_frame, text="Detector:").grid(row=1, column=2, padx=5, pady=5, sticky="w")
        self.detector_dropdown = tk.Listbox(input_frame, selectmode="multiple", height=3)
        for det in ["L1", "H1", "V1"]:
            self.detector_dropdown.insert(tk.END, det)
        self.detector_dropdown.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        

        # GPS Time Inputs
        ttk.Label(input_frame, text="Start Time:").grid(row=0, column=2, padx=5, pady=5, sticky="w")
        self.gps_start_entry = ttk.Entry(input_frame, width=20)
        self.gps_start_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="End Time (Optional):").grid(row=0, column=4, padx=5, pady=5, sticky="w")
        self.gps_end_entry = ttk.Entry(input_frame, width=20)
        self.gps_end_entry.grid(row=0, column=5, padx=5, pady=5, sticky="ew")

        # FFT & Method Inputs
        ttk.Label(input_frame, text="FFT Length:").grid(row=1, column=4, padx=5, pady=5, sticky="w")
        self.fft_length_entry = ttk.Entry(input_frame, width=10)
        self.fft_length_entry.grid(row=1, column=5, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="Window:").grid(row=1, column=6, padx=5, pady=5, sticky="w")
        self.window_entry = ttk.Combobox(input_frame, width=10, values=["hann", "option2"], state="readonly")
        self.window_entry.grid(row=1, column=7, padx=5, pady=5, sticky="ew")
        self.window_entry.current(0)
        
        ttk.Label(input_frame, text="Overlap duration").grid(row=2, column=4, padx=5, pady=5, sticky="w")
        self.overlap_entry = ttk.Entry(input_frame, width=20)
        self.overlap_entry.grid(row=2, column=7, padx=5, pady=5, sticky="ew")

        # GPS ⇄ UTC Converter
        self.mode = tk.StringVar(value="gps_to_utc")
        conversion_frame = ttk.LabelFrame(self.frame, text="GPS ⇄ UTC Converter")
        conversion_frame.grid(row=1, column=0, padx=5, pady=5, sticky="nsew")

        self.convert_entry = ttk.Entry(conversion_frame, width=20)
        self.convert_entry.grid(row=0, column=0, padx=5, pady=5)

        self.convert_button = ttk.Button(conversion_frame, text="Convert", command=self.convert_time)
        self.convert_button.grid(row=0, column=1, padx=5, pady=5)

        self.result_label = ttk.Label(conversion_frame, text="Result: ")
        self.result_label.grid(row=0, column=2, padx=5, pady=5)

        self.toggle_button = ttk.Button(conversion_frame, text="Switch to UTC → GPS", command=self.toggle_mode)
        self.toggle_button.grid(row=0, column=3, padx=5, pady=5)
        

        self.prefetch_data()
        self.plot_button = tk.Button(root, text="Plot TimeSeries", command=lambda: self.specgrams([self.detector_dropdown.get(idx) for idx in self.detector_dropdown.curselection()],gps_start=float(self.gps_start_entry.get()),gps_end = float(self.gps_end_entry.get()),fftlengths=int(self.fft_length_entry.get()),window=self.window_entry.get(),overlap=self.overlap_entry.get()))
        self.plot_button.grid(row=0, column=3, columnspan=2, pady=10)

    # 🔹 Prefetch Catalogs & Runs at Startup
    def prefetch_data(self):
        try:
            catalogs = find_datasets(type="catalog")
            self.catalog_dropdown["values"] = catalogs
            if catalogs:
                self.catalog_dropdown.current(0)

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching catalogs: {e}")

    # 🔹 Fetch Events Based on Selected Catalog
    def fetch_events(self, event=None):
        selected_catalog = self.catalog_dropdown.get()
        if not selected_catalog:
            return
        try:
            events = datasets.find_datasets(type="events", catalog=selected_catalog)
            self.event_dropdown["values"] = events
            if events:
                self.event_dropdown.current(0)
                self.fetch_event_details()  # Auto-update details for first event

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching events: {e}")

    # 🔹 Fetch Event GPS & URLs
    def fetch_event_details(self, event=None):
        selected_event = self.event_dropdown.get()
        if not selected_event:
            return
        try:
            gps_time = event_gps(selected_event)
            self.gps_start_entry.delete(0, tk.END)
            self.gps_start_entry.insert(0, str(gps_time))

            

        except Exception as e:
            messagebox.showerror("Error", f"Error fetching event details: {e}")

    # 🔹 Toggle GPS ⇄ UTC Mode
    def toggle_mode(self):
        if self.mode.get() == "gps_to_utc":
            self.mode.set("utc_to_gps")
            self.toggle_button.config(text="Switch to GPS → UTC")
        else:
            self.mode.set("gps_to_utc")
            self.toggle_button.config(text="Switch to UTC → GPS")

    # 🔹 Convert GPS ⇄ UTC
    def convert_time(self):
        time_input = self.convert_entry.get().strip()
        if not time_input:
            messagebox.showerror("Error", "Please enter a valid time!")
            return
        try:
            if self.mode.get() == "gps_to_utc":
                gps_time = float(time_input)
                utc_time = gp_time.from_gps(int(gps_time))
                self.result_label.config(text=f"UTC Time: {utc_time}")
            else:
                utc_time = datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
                gps_time = gp_time.to_gps(utc_time)
                self.result_label.config(text=f"GPS Time: {gps_time}")

        except Exception as e:
            messagebox.showerror("Error", f"Conversion failed: {e}")
 

    def specgrams(self, detectors, gps_start, gps_end, fftlengths, window,overlap):

        fig, ax = plt.subplots(figsize=(8, 5))
        for i, det in enumerate(detectors):
            try:
                # Fetch GWOSC data
                print(i,det)
                data = TimeSeries.fetch_open_data(det, gps_start, gps_end,cache=True)
                print(data)
                specgram = data.spectrogram2(fftlength=fftlengths, overlap=overlap, window=window) ** (1/2.)
                plot = specgram.plot()
                ax = plot.gca()
                ax.set_yscale('log')
                ax.set_ylim(10, 1400)
                ax.colorbar(
                    clim=(1e-24, 1e-20),
                    norm="log",
                    label=r"Strain noise [$1/\sqrt{\mathrm{Hz}}$]",
                )
            except Exception as e:
                print(f"Error fetching data for {det}: {e}")

        canvas = FigureCanvasTkAgg(plot, master=self.root)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.grid(row=2, column=0, columnspan=4, sticky="nsew")
        canvas.draw()

        # Add Matplotlib toolbar
        toolbar_fft = NavigationToolbar2Tk(canvas, self.root)
        toolbar_fft.grid(row=3, column=0, columnspan=1, pady=5)

        # Save Button
        def save_plot():
            file_path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png"), ("All Files", "*.*")])
            if file_path:
                fig.savefig(file_path)
                print(f"Plot saved as {file_path}")

        save_button = tk.Button(self.root, text="Save Plot", command=save_plot)
        save_button.grid(row=3, column=1, pady=5)

        # Configure grid for resizing
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

#########################################################################################################################################################################
if __name__ == "__main__":
    root = tk.Tk()
    app = Application(root)
    root.mainloop()
    cef.Shutdown()  # Ensure CEF shuts down properly