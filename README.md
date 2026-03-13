# BlackJack Simluation

blackjack_sim/
├── main.py                # Entry point: loads config and runs the loop
├── config.json            # Table rules and player/strategy mapping
├── engine/
│   ├── __init__.py
│   ├── models.py          # Card, Deck, Hand classes
│   ├── participants.py    # Participant (Base), Player, Dealer classes
│   └── controller.py      # Game class (the orchestrator)
├── strategies/
│   ├── __init__.py
│   ├── base.py            # Abstract Strategy interface
│   ├── basic_strategy.py  # Standard book play
│   └── card_counter.py    # High-low counting logic
└── results/               # CSVs and plots of chip movement


The "Strategy-to-Player" Factory

```python
class StrategyFactory:
    _mapping = {
        "basic": BasicStrategy,
        "aggressive": AggressiveStrategy,
        "counter": CardCounter
    }
    @staticmethod
    def create(name):
        return StrategyFactory._mapping[name.lower()]()
```


Simulation Flow
The Game class runs the "Clock" of the simulation.

Initialize: Load config.json. Use the StrategyFactory to build the player roster.

Betting: Each player queries their BettingStrategy to place chips on the table.

The Deal: Deck distributes cards.

The Action:

Game loops through players.

Each player asks their Strategy module: "What is my move?"

Player executes hit(), stand(), split(), or double().

Resolution: Dealer plays. Game settles bets and logs the new chip totals to the history tracker.

Key Design Features
Hot-Swappable Rules: Change payout_ratio (3:2 vs 6:5) or decks_in_shoe in the JSON without touching the Python code.

Multi-Hand Support: The Player class holds a list of Hand objects, making Splitting naturally supported.

Analytics Ready: Because every Player tracks their chip_history in a list, you can export the data at the end of 10,000 rounds to create a "Chip Movement" graph.
