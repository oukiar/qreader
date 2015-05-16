
from parse_rest.connection import register
from parse_rest.datatypes import Object

class GameScore(Object):
    pass


register("XEPryFHrd5Tztu45du5Z3kpqxDsweaP1Q0lt8JOb", "PE8FNw0hDdlvcHYYgxEnbUyxPkP9TAsPqKvdB4L0")

myClassName = "GameScore"
myClass = Object.factory(myClassName)

print myClass

gameScore = GameScore(score=1337, player_name='John Doe', cheat_mode=False)

gameScore.cheat_mode = True
gameScore.level = 2

gameScore.save()

