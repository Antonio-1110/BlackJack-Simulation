from blackjack import Game
import csv
import json

with open('config.json', 'r') as f:
    config = json.load(f)
sim_rd = config["Sim_rounds"]
NoP = config["Number_of_Players"]
NoD = config["Number_of_Decks"]

#Simulation

if __name__ == "__main__":
    data = []
    temp = Game(NoD,NoP)
    for i in range(1,sim_rd+1):
        temp.sim()
        rd = [f"Round_{str(i)}",str(temp.house.points[-1])]
        for p in temp.players:
            rd.append(str(temp.players[p].points[-1]))
        rd.append(temp.exportcards())
        data.append(rd)
        temp.reset()

    # exporting CSV

    with open("Sim_rd:" + str(sim_rd) + "_NoP:" + str(NoP) + "_NoD:" + str(NoD), 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Rounds','Dealer'] + [f'Player_{str(i)}' for i in range(1,NoP+1)] + ['Card_Code'])
        writer.writerows(data)

# current table change to win or lose
# output table for specific player's performance