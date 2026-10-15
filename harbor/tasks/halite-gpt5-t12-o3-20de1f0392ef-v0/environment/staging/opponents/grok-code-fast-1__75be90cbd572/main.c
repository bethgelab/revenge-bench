#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

int get_direction_towards(int from_x, int from_y, int to_x, int to_y, int width, int height) {
    int dx = to_x - from_x;
    int dy = to_y - from_y;
    if (dx > width / 2) dx -= width;
    if (dx < -width / 2) dx += width;
    if (dy > height / 2) dy -= height;
    if (dy < -height / 2) dy += height;
    if (abs(dx) > abs(dy)) {
        if (dx > 0) return EAST;
        else return WEST;
    } else {
        if (dy > 0) return SOUTH;
        else return NORTH;
    }
}

#define BOT_NAME "MyCBot"

int main(void) {

    GAME game;
    int best_target_x, best_target_y, max_prod;
    int x, y, direction;
    int dirs[4] = {NORTH, EAST, SOUTH, WEST};
    int **targeted;

    srand(time(NULL));

    game = GetInit();
    targeted = __new_2d_int_array(game.width, game.height);
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        best_target_x = -1;
        best_target_y = -1;
        max_prod = 0;
        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == 0 && game.production[x][y] > max_prod) {
                    max_prod = game.production[x][y];
                    best_target_x = x;
                    best_target_y = y;
                }
            }
        }

        // Reset targeted
        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                targeted[x][y] = 0;
            }
        }

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    int best_dir = STILL;
                    int i;
                    int can_attack = 0;
                    // First, check for attack opportunities
                    for (i = 0; i < 4; i++) {
                        SITE adj = GetSiteFromMovement(game, x, y, dirs[i]);
                        // Check for attack opportunity, if not targeted
                        if (adj.owner != 0 && adj.owner != game.playertag && game.strength[x][y] > adj.strength && targeted[adj.x][adj.y] == 0) {
                            best_dir = dirs[i];
                            targeted[adj.x][adj.y] = 1;
                            can_attack = 1;
                            break; // Prioritize attack
                        }
                    }
                    // If no attack, check for expansion
                    if (!can_attack) {
                        if (best_target_x != -1) {
                            best_dir = get_direction_towards(x, y, best_target_x, best_target_y, game.width, game.height);
                            SITE adj = GetSiteFromMovement(game, x, y, best_dir);
                            if (adj.owner == 0 && game.strength[x][y] > 0 && targeted[adj.x][adj.y] == 0) {
                                targeted[adj.x][adj.y] = 1;
                            } else {
                                best_dir = STILL;
                            }
                        }
                    }
                    // If no good move and surrounded by enemies, stay to build strength
                    if (best_dir == STILL && !can_attack) {
                        int enemy_count = 0;
                        for (i = 0; i < 4; i++) {
                            SITE adj = GetSiteFromMovement(game, x, y, dirs[i]);
                            if (adj.owner != 0 && adj.owner != game.playertag) {
                                enemy_count++;
                            }
                        }
                        if (enemy_count >= 3) { // Surrounded, stay still
                            best_dir = STILL;
                        }
                    }
                    SetMove(game, x, y, best_dir);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}