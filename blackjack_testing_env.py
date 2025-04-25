import random
import blackjack as bj

temp = bj.Game(3,3)
temp.sim()
print(temp.house.points)
for i in temp.players:
    print(temp.players[i].status, temp.players[i].points)