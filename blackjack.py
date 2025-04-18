import random
import math
import statistics

def newdeck(x):
    deck = []
    color = ["Spade","Heart","Diamond","Club"]
    for t in range(x):
        for i in range (1,14):
            for s in color:
                deck.append((i,s))
    random.shuffle(deck)
    return deck

class base():

    def __init__(self):
        self.cards = []
        self.status = "live"

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

class Player(base):

    def __init__(self):
        super().__init__()

    def linear_strat(self, gameDeck, stopUntil = 16):
        if self.status == "live":
            if self.points[-1] < 12: #hit when less than 12
                self.hit(gameDeck)
                self.linear_strat(gameDeck)
            elif self.points[-1] > stopUntil:
                pass
            else:
                if len(self.points) > 1: # if soft hand and upper limit less than stopUntil hit regardless
                    self.hit(gameDeck)
                elif round(random.uniform(0,1), 4) <= round((21-self.points[-1])/13,4):
                    print("h")
                    self.hit(gameDeck)
                    self.linear_strat(gameDeck)
                
        def sigmoid_strat(self, gameDeck, house, ws, wh, stopUntil = 18):
            c = 1/(1+math.e^(-ws*(-self.points[-1]+14.5+wh*(house-7))))
            if self.status == "live":
                if self.points[-1] < 12: #hit when less than 12
                    self.hit(gameDeck)
                    self.linear_strat(gameDeck)
                elif self.points[-1] > stopUntil:
                    pass
                else:
                    if len(self.points) > 1: # if soft hand and upper limit less than stopUntil hit regardless
                        self.hit(gameDeck)
                    else:
                        pass

            

    def final(self,boss):
        self.points = [self.points[-1]]
        if self.status == "boom":
            pass
        elif boss.status == "boom":
            self.status = "win"
        else:
            if self.points[-1] > boss.points[-1]:
        
                self.status = "win"
            elif self.points[-1] < boss.points[-1]:
                self.status = "lose"
            else:
                self.status = "tie"


class Dealer(base):

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
        self.points = [self.points[-1]]

def winrate(players, boss):
    win = 0
    for p in players:
        players[p].final(boss)
        if players[p].status == "win":
            win+=1
    return win/len(players)

def boomrate(players, boss):
    boom = 0
    for p in players:
        players[p].final(boss)
        if players[p].status == "boom":
            boom+=1
    return boom/len(players)

class Game():
    def __init__(self, numOfDecks):
        self.numOfDeck = numOfDecks
        self.deck = newdeck(numOfDecks)
    def reshuffle(self):
        self.deck = newdeck(self.numOfDeck)
    def start(self,numOfPlayers):
        if len(self.deck) < (numOfPlayers+1)*6:
            self.reshuffle()
        self.players = dict()
        for i in range(1,numOfPlayers+1):
             self.players[f"Player {i}"] = Player()
        self.house = Dealer()
        for t in self.players:
            self.players[t].hit(self.deck)
        self.house.hit(self.deck)
        for t in self.players:
            self.players[t].hit(self.deck)
        
        # for i in range(1,numOfPlayers+1):
        #     self.players[f"Player {i}"].hit(deck)
        # for p in self.players:
        #     self.players[p].strat(coefficient,deck)
        # self.house.finish(deck)
        # self.updateStats()

    def mid(self,aggre = 2):
        for p in self.players:
            self.players[p].linear_strat(self.deck)

    def end(self):
        self.house.finish(self.deck) # can adjust house rule i.e. soft/hard and value
        for p in self.players:
            self.players[p].final(self.house)
        self.winrate = winrate(self.players, self.house)
        self.boomrate = boomrate(self.players, self.house)

    def getcards(self):
        for p in self.players:
            print(p,self.players[p].points,self.players[p].status,self.players[p].cards)
        print("Boss",self.house.points,self.house.status,self.house.cards)


# game as parent class and player and dealer as child class
# gameclass will contain the statistics of the round
# ace handling calculate minimum score then update aces if possible

# graph for different players and different strategy


temp = Game(3)
print(len(temp.deck))
temp.start(3)
temp.getcards()
temp.mid()
temp.end()
temp.getcards()
print("\n")
temp.start(4)
temp.getcards()
temp.mid()
temp.end()
temp.getcards()
print(len(temp.deck))