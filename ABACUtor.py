import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
from google_play_scraper import app
import threading
import time
from google import genai
import os
import sys
import tempfile

# --- Google API Clients ---
client = genai.Client(api_key="AIzaSyC6QK_uuh_Byxa8-8eOgk9J5r3n7lXMMAc")


# --- Stdout redirector for capturing print statements ---
class StdoutRedirector:
    def __init__(self, text_widget):
        self.text_widget = text_widget

    def write(self, message):
        self.text_widget.insert(tk.END, message)
        self.text_widget.see(tk.END)  # Auto-scroll to the end
        self.text_widget.update()

    def flush(self):
        pass


# --- Error logging list ---
error_log = []


def log_error(error_message):
    """Add an error message to the error log list."""
    error_log.append(error_message)


def save_error_log():
    """Prompt user to save the error log to a file if errors exist."""
    if not error_log:
        return  # No errors to save
    response = messagebox.askyesno("Save Error Log",
                                   "Errors occurred during Gemini processing. Would you like to save the error log to a file?")
    if response:
        log_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
            title="Save Error Log As",
            initialfile="error_log.txt"
        )
        if log_path:
            try:
                with open(log_path, 'w', encoding='utf-8') as log_file:
                    for error in error_log:
                        log_file.write(f"{error}\n")
                print(f"✅ Error log saved to: {log_path}")
            except Exception as log_err:
                print(f"❌ Failed to save error log: {log_err}")


def compare_csv_files(app_csv_path, gemini_csv_path, differences_file_path):
    """
	Compare the 'Package Name' column of app_categories.csv and gemini_categories.csv.
	Save any differences to a new CSV file.
	"""
    try:
        # Read only the 'Package Name' column from both files
        df_app = pd.read_csv(app_csv_path)[['Package Name']]
        df_gemini = pd.read_csv(gemini_csv_path)[['Package Name']]
    except FileNotFoundError:
        print(f"Error: One or both CSV files not found.")
        return
    except pd.errors.EmptyDataError:
        print("Error: One or both CSV files are empty.")
        return
    except KeyError:
        print("Error: 'Package Name' column not found in one or both CSV files.")
        return
    except Exception as e:
        print(f"An error occurred while reading CSV files: {e}")
        return

    # Find package names present in app_categories but not in gemini_categories
    app_only = df_app[~df_app['Package Name'].isin(df_gemini['Package Name'])]
    app_only['Source'] = 'App Categories CSV Only'

    # Find package names present in gemini_categories but not in app_categories
    gemini_only = df_gemini[~df_gemini['Package Name'].isin(df_app['Package Name'])]
    gemini_only['Source'] = 'Gemini Categories CSV Only'

    # Concatenate differences
    all_differences = pd.concat([app_only, gemini_only])

    if not all_differences.empty:
        try:
            all_differences.to_csv(differences_file_path, index=False)
            print(f"✅ Differences found and saved to: {differences_file_path}")
            print(f" - Package names in app_categories.csv ONLY: {len(app_only)}")
            print(f" - Package names in gemini_categories.csv ONLY: {len(gemini_only)}")
        except Exception as e:
            print(f"❌ Failed to save differences: {e}")
    else:
        print("✅ No differences found in 'Package Name' columns between app_categories.csv and gemini_categories.csv.")

    return all_differences


def process_file(input_path, output_path, skip_scraper=False):
    try:
        if not skip_scraper:
            # Original scraper logic
            df_input = pd.read_csv(input_path)
            if 'Package Name' not in df_input.columns:
                messagebox.showerror("Error", "CSV must contain a 'Package Name' column.")
                start_button.config(state='normal')
                return

            package_names = df_input['Package Name'].dropna().unique()
            results = []

            for packagecount, package in enumerate(package_names):
                try:
                    data = app(package)
                    results.append({
                        'Package Name': package,
                        'Category': data.get('genre', '')
                    })
                    status_label.config(text=f"{packagecount + 1}/{len(package_names)} - {package} ✔")
                except Exception:
                    results.append({
                        'Package Name': package,
                        'Category': 'App does not exist in Play Store'
                    })
                    status_label.config(text=f"{packagecount + 1}/{len(package_names)} - {package} ❌")
                time.sleep(0.1)

            df_output = pd.DataFrame(results)
            df_output.to_csv(output_path, index=False)
            print(f"✅ Google Play categories saved to: {output_path}")
        else:
            # Use the provided app_categories.csv
            print(f"✅ Using provided app_categories.csv: {output_path}")

        print(f"\n")

        # --- Gemini test file upload ---
        try:
            # Create a temporary TXT file for Gemini
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
                df_output = pd.read_csv(output_path)
                df_output.to_csv(temp_file.name, index=False)
                temp_file_path = temp_file.name

            # Upload the temporary TXT file to Gemini
            uploaded_file = client.files.upload(file=temp_file.name)
            print(f"✅ Uploaded file: {uploaded_file.name} (URI: {uploaded_file.uri})")

            # Generate content with Gemini using the uploaded file
            result = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    uploaded_file,
                    'You are given the contents of a CSV file. Extract every value from the first column (excluding the header row). '
                    'For each value, search the web or use external knowledge to generate a description. '
                    'Your task: '
                    'Output 1 sentence into the second column that describes the application and its functions/features and another to describe the UI elements on the landing page of the app in great detail. '
                    'Rules for output format: '
                    'Print headers exactly as: Package Name, Description. '
                    'Preserve the original order of package names. '
                    'Each line must follow this format: [package_name],[description_and_landing_page] (no brackets). '
                    'Do not change or alter any package name in any way. '
                    'Do not add extra commentary or explanation - only the data. '
                    'Use commas only as delimiters. The description text itself must not contain any commas. Use periods, semicolons, or dashes instead.'
                    'Ensure all package names are accounted for in the output. '
                    'The final output must be complete, ordered, and clean.'
                ]
            )
            print(f"\n")
            print(f"Gemini response:")
            print(f"\n")
            print(f"{result.text}")

            # Save result.text as CSV
            try:
                # Parse the Gemini response (assuming comma-separated text with headers)
                lines = result.text.strip().split('\n')
                if not lines or lines[0] != 'Package Name,Description':
                    raise ValueError("Unexpected Gemini response format. Expected 'Package Name,Category' header.")

                # Convert lines to list of [package_name, category] rows, skipping header
                data = [line.split(',') for line in lines[1:] if line.strip()]

                # Create DataFrame
                df_gemini = pd.DataFrame(data, columns=['Package Name', 'Category'])

                # Prompt user to save the CSV
                csv_path = filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("CSV Files", "*.csv")],
                    title="Save Gemini Response As",
                    initialfile="gemini_categories.csv"
                )

                if csv_path:
                    df_gemini.to_csv(csv_path, index=False, lineterminator='\n')
                    print(f"✅ Gemini response saved to: {csv_path}")

                    # Compare app_categories.csv and gemini_categories.csv
                    differences_file_path = os.path.splitext(csv_path)[0] + "_differences.csv"
                    all_differences = compare_csv_files(output_path, csv_path, differences_file_path)

                    # Update gemini_categories.csv based on differences
                    if not all_differences.empty:
                        try:
                            # Read the current gemini_categories.csv
                            df_gemini = pd.read_csv(csv_path)

                            # Filter for 'App Categories CSV Only' package names
                            app_only = all_differences[all_differences['Source'] == 'App Categories CSV Only']
                            if not app_only.empty:
                                # Create new rows for app_only packages with UNCATEGORIZED
                                new_rows = pd.DataFrame({
                                    'Package Name': app_only['Package Name'],
                                    'Category': ['UNCATEGORIZED'] * len(app_only)
                                })
                                # Append new rows to df_gemini
                                df_gemini = pd.concat([df_gemini, new_rows], ignore_index=True)

                            # Filter out 'Gemini Categories CSV Only' package names
                            gemini_only = all_differences[all_differences['Source'] == 'Gemini Categories CSV Only']
                            if not gemini_only.empty:
                                df_gemini = df_gemini[~df_gemini['Package Name'].isin(gemini_only['Package Name'])]

                            # Save the updated gemini_categories.csv
                            df_gemini.to_csv(csv_path, index=False, lineterminator='\n')
                            print(
                                f"✅ Updated {csv_path}: Added {len(app_only)} UNCATEGORIZED packages, removed {len(gemini_only)} Gemini-only packages.")
                            print(
                                f"‼️ If more than 10 apps were added as UNCATEGORIZED, please re-run using existing app_categories.csv file ‼️")
                        except Exception as update_err:
                            error_message = f"Failed to update gemini_categories.csv: {update_err}"
                            log_error(error_message)
                            print(f"❌ {error_message}")
                else:
                    print("❗ Gemini response CSV save canceled by user.")
            except Exception as csv_err:
                error_message = f"Failed to save Gemini response as CSV: {csv_err}"
                log_error(error_message)
                print(f"❌ {error_message}")

            # Clean up the temporary file
            os.unlink(temp_file_path)

        except Exception as gemini_err:
            print(f"❌ Gemini file upload or processing failed: {gemini_err}")
            log_error(str(gemini_err))
            save_error_log()
            error_log.clear()

    except Exception as e:
        messagebox.showerror("Processing Error", str(e))
    finally:
        start_button.config(state='normal')


def start_file_selection():
    # Check if the user wants to skip the scraper
    skip_scraper = skip_scraper_var.get()

    if not skip_scraper:
        # Original behavior: select input CSV and output location
        input_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv")],
            title="Select Your Input CSV File"
        )
        if not input_path:
            status_label.config(text="❗ No input file selected.")
            return

        output_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            title="Save Output File As",
            initialfile="app_categories.csv"
        )
        if not output_path:
            status_label.config(text="❗ Output location not selected.")
            return
    else:
        # Skip scraper: select existing app_categories.csv
        output_path = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv")],
            title="Select Existing app_categories.csv File",
            initialfile="app_categories.csv"
        )
        if not output_path:
            status_label.config(text="❗ No app_categories.csv file selected.")
            return
        # Validate the selected file has the required column
        try:
            df = pd.read_csv(output_path)
            if 'Package Name' not in df.columns:
                messagebox.showerror("Error", "Selected CSV must contain a 'Package Name' column.")
                return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read selected CSV: {e}")
            return
        input_path = output_path  # Use the same file as input for Gemini processing

    start_button.config(state='disabled')
    status_label.config(text="⏳ Processing started...")
    # Clear the log area before starting a new process
    log_text.delete(1.0, tk.END)
    threading.Thread(
        target=process_file, args=(input_path, output_path, skip_scraper), daemon=True
    ).start()


# --- GUI Setup ---
root = tk.Tk()
root.title("📦 ABACUtor")
root.geometry("600x500")  # Increased height to accommodate log area
root.resizable(False, False)

frame = tk.Frame(root, padx=20, pady=20)
frame.pack(expand=True, fill='both')

title_label = tk.Label(frame, text="📦 ABACUtor lol", font=('Helvetica', 14))
title_label.pack(pady=(0, 0))

# --- Credits and Contact ---
credit_label = tk.Label(frame, text="Program by Nathan Mercer. Contact: n.mercer@samsung.com", font=('Helvetica', 7),
                        fg="gray")
credit_label.pack(pady=(0, 12))

subtitle_label = tk.Label(frame, text="Please select package_list.csv file or use existing app_categories.csv",
                          font=('Helvetica', 9))
subtitle_label.pack(pady=(0, 13))

# Checkbox to skip Google Play scraper
skip_scraper_var = tk.BooleanVar()
skip_scraper_check = tk.Checkbutton(
    frame,
    text="Use existing app_categories.csv (skip Google Play scraper)",
    variable=skip_scraper_var,
    font=('Helvetica', 10)
)
skip_scraper_check.pack(pady=(0, 10))

start_button = tk.Button(frame, text="📂 Choose Input File & Save Location", command=start_file_selection, width=35)
start_button.pack(pady=6)

status_label = tk.Label(frame, text="Waiting for file selection...", font=('Helvetica', 10), fg="gray")
status_label.pack(pady=(10, 10))

# --- Log Area for Terminal Messages ---
log_frame = tk.Frame(frame)
log_frame.pack(fill='both', expand=True)

log_label = tk.Label(log_frame, text="Log Output:", font=('Helvetica', 10))
log_label.pack(anchor='w')

log_text = tk.Text(log_frame, height=5, width=50, font=('Helvetica', 9), wrap='word')
log_text.pack(side='left', fill='both', expand=True)

scrollbar = tk.Scrollbar(log_frame, orient='vertical', command=log_text.yview)
scrollbar.pack(side='right', fill='y')
log_text.config(yscrollcommand=scrollbar.set)

# Redirect print statements to the log_text widget
sys.stdout = StdoutRedirector(log_text)

root.mainloop()
