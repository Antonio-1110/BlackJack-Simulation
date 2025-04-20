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

class Base():

    def __init__(self):
        self.cards = []
        self.status = "live"
        self.points = [0]
        self.noAce = True

    def hit(self,deck):
        self.cards.append(deck.pop(0))
        self.points[0] += 10 if self.cards[-1][0] > 10 else self.cards[-1][0]
        if self.noAce and self.cards[-1][0] == 1:
            self.noAce = False
        if not self.noAce:
            self.points = [self.points[0]]
            if self.points[0] + 10 < 22:
                self.points.append(self.points[0]+10)
        

class Player(Base):

    def __init__(self):
        super().__init__()

    def linear_strat(self,gameDeck):
        if self.status == "live":
            if self.points[-1] < 12:
                self.hit(gameDeck)
                self.linear_strat(gameDeck)
            elif self.points[-1] > 17:
                pass
            else:
                p = round((21-self.points[-1])/13,4)
                if round(random.uniform(0,1), 4) <= p:
                    self.hit(gameDeck)
                    self.linear_strat(gameDeck)
            

    def final(self,boss):
        if self.status == "boom":
            pass
        elif boss.status == "boom":
            self.status = "win"
        else:
            if self.points > boss.points:
                self.status = "win"
            elif self.points < boss.points:
                self.status = "lose"
            else:
                self.status = "tie"

class Dealer(Base):
    def __init__(self):
        super().__init__()
    def finish(self,deck,value=17,hit_on_soft=True):
        if hit_on_soft:
            while len(self.points)>1 and self.points[-1]==value:
                self.hit(deck)
            while self.points[-1]<value:
                self.hit(deck)
        else:
            while self.points[-1]<value:
                self.hit(deck)

x = Player()
y = [(1,"t"),(10,"6"),(1,"5"),(1,"t")]
for i in range (len(y)):
    x.hit(y)
    print(x.cards,x.points)