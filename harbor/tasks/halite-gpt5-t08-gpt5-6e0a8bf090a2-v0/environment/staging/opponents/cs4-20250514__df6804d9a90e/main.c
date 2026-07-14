#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "SimpleEastBot"

int main(void) {
    GAME game;
    int x, y;

    srand(time(NULL));
    
    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {  // Continue until game ends naturally
        GetFrame(game);
        
        // Simple strategy: Move EAST when we can defeat the target
        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    // Check if we can move EAST
                    int target_x = (x + 1) % game.width;  // Wrap around map
                    int target_strength = game.strength[target_x][y];
                    int our_strength = game.strength[x][y];
                    
                    // Move EAST if we have enough strength to defeat target
                    if (our_strength > target_strength) {
                        SetMove(game, x, y, EAST);
                    } else {
                        SetMove(game, x, y, STILL);  // Stay still to build strength
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}