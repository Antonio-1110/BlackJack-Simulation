import customtkinter as ctk
from tkinter import messagebox
import json
import blackjack_sim_env as bjs

CONFIG_FILE = 'config.json'

ctk.set_appearance_mode("Dark")

class BlackjackConfigGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Blackjack Simulation Configurator")
        self.geometry("400x250")
        self.resizable(False, False)
        self.custom_font = ("Calibri", 16)
        self.vardict = dict()

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
        ctk.CTkLabel(self, text="Number of Decks:", font = self.custom_font).grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.vardict['Number_of_Decks'] = ctk.StringVar(value=str(self.config_data.get('Number_of_Decks', 3)))
        ctk.CTkEntry(self, textvariable=self.vardict['Number_of_Decks']).grid(row=0, column=1, padx=10, pady=10)

        # Number of Players
        ctk.CTkLabel(self, text="Number of Players:", font = self.custom_font).grid(row=1, column=0, padx=10, pady=10, sticky='w')
        self.vardict['Number_of_Players'] = ctk.StringVar(value=str(self.config_data.get('Number_of_Players', 3)))
        ctk.CTkEntry(self, textvariable=self.vardict['Number_of_Players']).grid(row=1, column=1, padx=10, pady=10)

        # Number of Simulations
        ctk.CTkLabel(self, text="Simulated Rounds:", font = self.custom_font).grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.vardict['Simulated_rounds'] = ctk.StringVar(value=str(self.config_data.get('Simulated_rounds', 1000)))
        ctk.CTkEntry(self, textvariable=self.vardict['Simulated_rounds']).grid(row=2, column=1, padx=10, pady=10)

        #Strategy Selection
        ctk.CTkLabel(self, text="Strategy Used:", font= self.custom_font).grid(row=3, column=0, padx =10, pady=10, sticky="w")
        self.strategy_var = ctk.StringVar(value=str(self.config_data.get('Strategy', "Linear")))
        ctk.CTkComboBox(self, values=["Linear", "Sigmoid", "Discrete"],variable=self.strategy_var).grid(row=3, column=1, padx=10, pady=10)

        # Save Button
        ctk.CTkButton(self, text="Save Config", font = self.custom_font, command=self.save_config).grid(row=4, column=0, padx=10, pady=20)

        # Run Simulation Button
        ctk.CTkButton(self, text="Run Simulation", font = self.custom_font, command=self.run_simulation).grid(row=4, column=1, padx=10, pady=20)

    def process(self):

        for i in self.vardict:
            try:
                self.config_data[i] = int(self.vardict[i].get())
            except ValueError:
                messagebox.showerror("Error", f"Invalid Input ({self.vardict[i].get()})\n Please enter valid integers for {i.replace("_", " ")}")
                return False
            self.config_data["Strategy"] = str(self.strategy_var.get())

        try:
            with open(CONFIG_FILE, 'w') as file:
                json.dump(self.config_data, file, indent=4)
                return True
        except IOError as e:
            messagebox.showerror("Error", f"Failed to save configuration:\n{e}")
            return False

    def save_config(self):
        if self.process():
            messagebox.showinfo("Success", "Configuration saved successfully.")

    def run_simulation(self):
        if self.process():
            try:
                if bjs.simulation():
                    messagebox.showinfo(
                        "Success",
                        f"Simulated with {self.config_data['Simulated_rounds']} rounds, {self.config_data['Number_of_Players']} players and {self.config_data['Number_of_Decks']} decks using {self.config_data["Strategy"]} Strategy"
                    )
                else:
                    messagebox.showerror("Error", "Simulation failed")
            except Exception as e:
                messagebox.showerror("Error", f"Simulation failed: {e}")

if __name__ == "__main__":
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = BlackjackConfigGUI()
    app.mainloop()
