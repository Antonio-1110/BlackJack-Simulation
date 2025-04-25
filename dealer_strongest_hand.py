from blackjack import Dealer, newdeck
from statistics import mean

data = dict()

for i in range(1,14):
    dealer_uppercard = (i,"Spade")

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

    data[dealer_uppercard] = (mean(rate),mean(points))

print(data)

# {(1, 'Spade'): (0.1189, 20.0415),   (2, 'Spade'): (0.3496, 20.4816),  (3, 'Spade'): (0.3758, 20.6003), 
#  (4, 'Spade'): (0.4033, 20.8235),   (5, 'Spade'): (0.4245, 21.0046),  (6, 'Spade'): (0.4291, 21.0767), 
#  (7, 'Spade'): (0.2582, 19.5457),   (8, 'Spade'): (0.2449, 19.7256),  (9, 'Spade'): (0.2314, 19.9957), 
#  (10, 'Spade'): (0.2166, 20.2267), (11, 'Spade'): (0.2219, 20.2707), (12, 'Spade'): (0.2163, 20.2464), 
#  (13, 'Spade'): (0.2196, 20.2878)}