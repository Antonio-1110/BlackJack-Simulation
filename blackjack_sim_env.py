from blackjack import Game
from blackjack import Player
import csv
import json
import os

def simulation():

    with open('config.json', 'r') as f:
        config = json.load(f)
        f.close()

    stratdict = {"Linear":Player.linear_strat,"Sigmoid":Player.sigmoid_strat,"Discrete":Player.discrete_strat}

    #Simulation

    data = []
    temp = Game(config["Number_of_Decks"],config["Number_of_Players"])
    for i in range(1,config["Simulated_rounds"]+1):
        temp.rdsim(stratdict[config["Strategy"]])
        rd = [f"Round_{str(i)}",str(temp.house.points[-1])]
        for p in temp.players:
            rd.append(str(temp.players[p].points[-1]))
            rd.append(temp.players[p].status)
        rd.append(temp.exportcards())
        data.append(rd)
        temp.reset()

    # exporting CSV
    try:
        os.makedirs(config["Folder_Name"], exist_ok=True)
    except PermissionError:
        print(f"Permission denied: Unable to create '{config["Folder_Name"]}'.")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

    with open(config["Folder_Name"]+"/" + str(config["Simulated_rounds"]) + "Rd_" + str(config["Number_of_Players"])  + "P_" + str(config["Number_of_Decks"]) + "D-" + str(config["Strategy"])[:1] + ".csv", "w+") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Rounds','Dealer'] + [f'P{i}' if j % 2 == 0 else f'P{i}_status' for i in range(1, config["Number_of_Players"] + 1) for j in range(2)] + ['Card_Code'])
        writer.writerows(data)
        csvfile.close()

    return True

# output table for specific player's performance


if __name__ == '__main__' :
    simulation()