Number_of_Players = 3
Number_of_Decks = 3
sim_rounds = 100
fileheaders = ['Rounds','Dealer'] + [f'Player_{str(i)}' for i in range(1,Number_of_Players+1)] + ['Card_Code']
dataFileName = "Sim_rd_" + str(sim_rounds) + "_NoP_" + str(Number_of_Players) + "_NoD_" + str(Number_of_Decks)