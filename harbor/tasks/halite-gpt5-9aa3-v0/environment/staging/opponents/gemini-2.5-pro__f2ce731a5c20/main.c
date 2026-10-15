#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot"
#define STRENGTH_BUILD_MULTIPLIER 3

// Function to shuffle an array of integers
void shuffle(int *array, size_t n) {
    if (n > 1) {
        size_t i;
        for (i = 0; i < n - 1; i++) {
            size_t j = i + rand() / (RAND_MAX / (n - i) + 1);
            int t = array[j];
            array[j] = array[i];
            array[i] = t;
        }
    }
}

int main(void) {

    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);
        SITE neighbor;
        int direction;
        int directions[] = {1, 2, 3, 4}; // N, E, S, W


        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    if (game.strength[x][y] > game.production[x][y] * STRENGTH_BUILD_MULTIPLIER) {
                        direction = STILL;
                        shuffle(directions, 4); // Shuffle directions
                        for (int i = 0; i < 4; i++) {
                            int d = directions[i];
                            neighbor = GetSiteFromMovement(game, x, y, d);
                            if (neighbor.owner != game.playertag && game.strength[x][y] > neighbor.strength) {
                                direction = d;
                                break;
                            }
                        }

                        SetMove(game, x, y, direction);
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}