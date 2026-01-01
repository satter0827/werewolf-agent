class GameEngine:
    def __init__(self) -> None:
        self.state = "initialized"

    def start_game(self) -> None:
        self.state = "running"
        print("Game started.")

    def end_game(self) -> None:
        self.state = "ended"
        print("Game ended.")
