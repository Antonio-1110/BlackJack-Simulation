import random

def newdeck(x):
    deck = []
    color = ["Spade","Heart","Diamond","Club"]
    for t in range(x):
        for i in range (1,14):
            for s in color:
                deck.append((i,s))
    random.shuffle(deck)
    return deck

dealeroriginal = 3
dealersec = []
dealerthird = []
dealerfourth = []
if dealeroriginal < 17:
    for i in range(1,11):
        dealersec.append(dealeroriginal+i)
    for i in dealersec:
        temp = []
        for t in range(1,11):
            if i < 17:
                temp.append(i+t)
        dealerthird.append(temp)
    for i in dealerthird:
        temp = []
        for y in i:
            for t in range(1,11):
                if y < 17:
                    temp.append(y+t)
            dealerfourth.append(temp)
    

print(dealersec)
print(dealerthird)
print(dealerfourth)
