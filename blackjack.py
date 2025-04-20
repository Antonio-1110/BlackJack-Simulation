import random
import math

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

    def calpoints(self):
            for card in self.cards:
                self.points[0] += 10 if card[0] > 10 else card[0]
                if card[0] == 1:
                     haveAce = True
            if haveAce and self.points[0]+10 < 22:
                self.points.append(self.points[0]+10)

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

    def __init__(self, numOfDecks, numOfPlayers):
        self.numOfDeck = numOfDecks
        self.deck = newdeck(numOfDecks)
        self.nOP = numOfPlayers
        self.players = dict()
        for i in range(1,numOfPlayers+1):
             self.players[f"Player {i}"] = Player()
        self.house = Dealer()

    def reshuffle(self):
        self.deck = newdeck(self.numOfDeck)

    def exportcards(self):
        temp = "d"
        for c in self.house.cards:
            temp+= str(c[0])+c[1][:1]
        for p in self.players:
            temp+= p[:1]+p[-1]
            for i in self.players[p].cards:
                temp+= str(i[0])+i[1][:1]
        return temp

    def sim(self,aggre = 2):
        if len(self.deck) < (len(self.players)+1)*5:
            self.reshuffle()
        for s in self.players:
            self.players[s].hit(self.deck)
        self.house.hit(self.deck)
        for s2 in self.players:
            self.players[s2].hit(self.deck)

        for m in self.players:
            self.players[m].linear_strat(self.deck) # make it so the streategy can be changed through config file
        self.house.finish(self.deck) # can adjust house rule i.e. soft/hard and value

        for e in self.players:
            self.players[e].final(self.house)

    def clean(self):
        self.players = dict()
        for i in range(1,self.nOP+1):
             self.players[f"Player {i}"] = Player()
        self.house = Dealer()
        
# diff player will have diff strategy

