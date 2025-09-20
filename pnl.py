#open csv

#betting amount diff pattern

#visualization loss or gains
import pandas as pd


df = pd.read_csv("Simulations/1000Rd_4P_3D-L.csv")

baseBet = 20
currentBet = baseBet
balance = 0
highest = 0
losestreak = False
for i in df["P1_status"]:
    if losestreak:
        currentBet*=2
    if currentBet > highest:
        highest = currentBet
    print("balance", balance)
    print("current bet", currentBet)
    print("lose streak", losestreak)
    print("result",i)
    if i == "win":
        balance += currentBet
        currentBet = baseBet
        losestreak = False
    elif i =="tie":
        pass
    else:
        balance -= currentBet
        losestreak = True

print(balance)
print(highest)