import tkinter as tk
from tkinter import ttk, messagebox
import json
import subprocess
import blackjack_sim_env as bjs

CONFIG_FILE = 'config.json'

class BlackjackConfigGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Blackjack Simulation Configurator")
        self.geometry("400x250")
        self.resizable(False, False)

        self.config_data = self.load_config()
        self.create_widgets()

    def load_config(self):
        try:
            with open(CONFIG_FILE, 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            messagebox.showerror("Error", f"{CONFIG_FILE} not found.")
            self.destroy()
        except json.JSONDecodeError:
            messagebox.showerror("Error", f"Error decoding {CONFIG_FILE}.")
            self.destroy()

    def create_widgets(self):
        # Number of Decks
        ttk.Label(self, text="Number of Decks:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.num_decks_var = tk.IntVar(value=self.config_data.get('Number_of_Decks', 3))
        ttk.Entry(self, textvariable=self.num_decks_var).grid(row=0, column=1, padx=10, pady=10)

        # Player Strategy
        ttk.Label(self, text="Number of Players:").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        self.num_player_var = tk.IntVar(value=self.config_data.get('Number_of_Players', 3))
        ttk.Entry(self, textvariable=self.num_player_var).grid(row=1, column=1, padx=10, pady=10)

        # Number of Simulations
        ttk.Label(self, text="Simulated Rounds:").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.sim_rd_var = tk.IntVar(value=self.config_data.get('Sim_rounds', 1000))
        ttk.Entry(self, textvariable=self.sim_rd_var).grid(row=2, column=1, padx=10, pady=10)

        # Save Button
        ttk.Button(self, text="Save Config", command=self.save_config).grid(row=3, column=0, padx=10, pady=20)

        # Run Simulation Button
        ttk.Button(self, text="Run Simulation", command=self.run_simulation).grid(row=3, column=1, padx=10, pady=20)

    def save_config(self):
        self.config_data['Number_of_Decks'] = self.num_decks_var.get()
        self.config_data['Sim_rounds'] = self.sim_rd_var.get()
        self.config_data['Number_of_Players'] = self.num_player_var.get()

        try:
            with open(CONFIG_FILE, 'w') as file:
                json.dump(self.config_data, file, indent=4)
            messagebox.showinfo("Success", "Configuration saved successfully.")
        except IOError as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n{e}")

    def run_simulation(self):
        try:
            subprocess.run(['python', 'blackjack_sim_env.py'], check=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Error", f"Simulation failed:\n{e}")

if __name__ == "__main__":
    app = BlackjackConfigGUI()
    app.mainloop()
