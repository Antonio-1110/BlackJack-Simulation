from blackjack import Dealer, newdeck
from statistics import mean

dealer_uppercard = (6,"Spade")

rate = []
points = []
house = Dealer()

for i in range(10000):
    deck = newdeck(3)
    deck.remove(dealer_uppercard)
    house.hit([dealer_uppercard])
    house.finish(deck)
    points.append(house.points[-1])
    rate.append(1 if house.points[-1] > 21 else 0)
    house.clean()

print(mean(rate), mean(points))