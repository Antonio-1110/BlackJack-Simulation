import blackjack
import config
import csv

if __name__ == "__main__":
    data = []
    temp = blackjack.Game(config.Number_of_Decks,config.Number_of_Players)
    for i in range(1,config.sim_rounds+1):
        temp.sim()
        rd = [f"Round_{str(i)}",str(temp.house.points[-1])]
        for p in temp.players:
            rd.append(str(temp.players[p].points[-1]))
        rd.append(temp.exportcards())
        data.append(rd)
        temp.clean()

    with open(config.dataFileName, 'w') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(config.fileheaders)
        writer.writerows(data)

# current table change to win or lose
# output table for specific player's performance