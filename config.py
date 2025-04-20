
dataFileName = "test"
Number_of_Players = 3
Number_of_Decks = 3
sim_rounds = 100

def field():
    temp = ['Rounds','Dealer']
    for i in range(1,Number_of_Players+1):
        temp.append(f'Player_{str(i)}')
    temp.append('Card_Code')
    return temp

fileheaders = field()