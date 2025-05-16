import blackjack as bj
from statistics import mean
import json


def calc_dbr():
    with open("config.json", "r") as f:
        config = json.load(f)

    data = dict()

    for i in range(1,14):
        dealer_uppercard = (i,"Spade")

        rate = []
        points = []
        house = bj.Dealer()

        for i in range(config["Simulated_rounds"]):
            deck = bj.newdeck(config["Number_of_Decks"])
            deck.remove(dealer_uppercard)
            house.hit([dealer_uppercard])
            house.finish(deck)
            points.append(house.points[-1])
            rate.append(1 if house.points[-1] > 21 else 0)
            house.clean()

        data[dealer_uppercard[0]] = (mean(rate),mean(points))
    return data

# {(1, 'Spade'): (0.1189, 20.0415),   (2, 'Spade'): (0.3496, 20.4816),  (3, 'Spade'): (0.3758, 20.6003), 
#  (4, 'Spade'): (0.4033, 20.8235),   (5, 'Spade'): (0.4245, 21.0046),  (6, 'Spade'): (0.4291, 21.0767), 
#  (7, 'Spade'): (0.2582, 19.5457),   (8, 'Spade'): (0.2449, 19.7256),  (9, 'Spade'): (0.2314, 19.9957), 
#  (10, 'Spade'): (0.2166, 20.2267), (11, 'Spade'): (0.2219, 20.2707), (12, 'Spade'): (0.2163, 20.2464), 
#  (13, 'Spade'): (0.2196, 20.2878)}

if __name__ == "__main__":
    print(calc_dbr())