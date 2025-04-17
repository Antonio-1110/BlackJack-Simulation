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

class test():
    def __init__(self):
         self.cards = []

    def calpoints(self):
            self.points = [0]
            haveAce = False
            for card in self.cards:
                self.points[0] += 10 if card[0] > 10 else card[0]
                if card[0] == 1:
                     haveAce = True
            if haveAce and self.points[0]+10 < 22:
                self.points.append(self.points[0]+10)

    def hit(self,deck):
        self.cards.append(deck.pop(0))
        self.calpoints()
        if self.points[0]>21:
            self.status = "boom"

class player(test):

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

class dealer(test):
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

x = player()
y = [(1,"t"),(7,"6"),(1,"5"),(13,"t")]
x.hit(y)
print(x.cards,x.points)
x.finish(y)
print(x.cards,x.points)