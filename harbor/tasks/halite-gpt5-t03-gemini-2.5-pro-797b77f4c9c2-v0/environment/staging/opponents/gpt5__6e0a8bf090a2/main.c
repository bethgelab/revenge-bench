#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "HeuristicCPlus"

static int dirs[4] = {NORTH, EAST, SOUTH, WEST};

static inline int is_owned(GAME game, int x, int y) {
    return game.owner[x][y] == game.playertag;
}

static inline SITE neighbor(GAME game, int x, int y, int dir) {
    return GetSiteFromMovement(game, x, y, dir);
}

static inline int opposite(int d) {
    if (d == NORTH) return SOUTH;
    if (d == SOUTH) return NORTH;
    if (d == EAST)  return WEST;
    return EAST; // WEST
}

static int is_border(GAME game, int x, int y) {
    for (int i = 0; i < 4; i++) {
        SITE n = neighbor(game, x, y, dirs[i]);
        if (n.owner != game.playertag) return 1;
    }
    return 0;
}

// Find direction to nearest non-owned cell along cardinal rays.
// Returns a direction (N/E/S/W). If multiple are equal distance, prefer higher production at the first non-owned encountered.
static int dir_to_nearest_border(GAME game, int x, int y) {
    int best_dir = NORTH;
    int best_dist = game.width + game.height + 1;
    int best_first_prod = -1;

    for (int i = 0; i < 4; i++) {
        int dir = dirs[i];
        int step = 1;
        int dx = 0, dy = 0;
        if (dir == NORTH) dy = -1;
        else if (dir == SOUTH) dy = 1;
        else if (dir == EAST) dx = 1;
        else if (dir == WEST) dx = -1;

        int cx = x, cy = y;
        int found = 0;
        int first_prod = 0;

        // Search outward until we hit a non-owned site
        while (step <= game.width + game.height) {
            cx += dx;
            cy += dy;
            SITE s = GetSiteFromXY(game, cx, cy);
            if (s.owner != game.playertag) {
                found = 1;
                first_prod = s.production;
                break;
            }
            step++;
        }
        if (found) {
            if (step < best_dist || (step == best_dist && first_prod > best_first_prod)) {
                best_dist = step;
                best_first_prod = first_prod;
                best_dir = dir;
            }
        }
    }
    return best_dir;
}

int main(void) {

    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {

                if (!is_owned(game, x, y)) continue;

                SITE here = GetSiteFromXY(game, x, y);

                // Default action is to stay still
                int move = STILL;

                // If we have no strength, staying is optimal
                if (here.strength == 0) {
                    SetMove(game, x, y, move);
                    continue;
                }

                // Threshold to begin moving when not on border
                int move_threshold = here.production * 5;
                if (move_threshold < 15) move_threshold = 15;

                // Try to attack adjacent non-owned squares we can defeat.
                int best_attack_dir = STILL;
                int best_attack_score = -1000000;

                for (int i = 0; i < 4; i++) {
                    SITE n = neighbor(game, x, y, dirs[i]);
                    if (n.owner != game.playertag) {
                        // Only attack if we can win this turn
                        if (here.strength > n.strength) {
                            // Favor high production and low strength targets, with a bonus for enemy-owned tiles
                            int score = n.production * 6 - n.strength;
                            if (n.owner != 0) score += 25; // prioritize damaging enemy over neutral
                            if (score > best_attack_score) {
                                best_attack_score = score;
                                best_attack_dir = dirs[i];
                            }
                        }
                    }
                }

                if (best_attack_dir != STILL) {
                    move = best_attack_dir;
                } else {
                    int on_border = is_border(game, x, y);

                    if (on_border) {
                        // On border but cannot attack: try to make way for stronger units behind,
                        // otherwise wait to build strength. Spill outward if very strong to avoid capping.
                        int outward = dir_to_nearest_border(game, x, y);
                        int inward = opposite(outward);
                        SITE back = neighbor(game, x, y, inward);

                        if (back.owner == game.playertag) {
                            if (back.strength > here.strength && back.strength + here.strength <= 255) {
                                move = inward; // step back to let the stronger unit advance later
                            } else if (here.strength > 240) {
                                move = outward; // prevent capping and encourage flow
                            } else {
                                move = STILL;
                            }
                        } else {
                            if (here.strength > 240) {
                                move = outward;
                            } else {
                                move = STILL;
                            }
                        }
                    } else {
                        // Interior cell: build up, then flow toward the edge while avoiding overflow
                        if (here.strength >= move_threshold || here.strength > 200) {
                            int d = dir_to_nearest_border(game, x, y);
                            SITE nxt = neighbor(game, x, y, d);
                            if (nxt.owner == game.playertag) {
                                if (here.strength + nxt.strength <= 255) {
                                    move = d;
                                } else {
                                    move = STILL; // avoid wasting strength due to cap
                                }
                            } else {
                                // Rare for interior; only move if we can capture safely
                                if (here.strength > nxt.strength) move = d; else move = STILL;
                            }
                        } else {
                            move = STILL;
                        }
                    }
                }

                SetMove(game, x, y, move);
            }
        }

        SendFrame(game);
    }

    return 0;
}