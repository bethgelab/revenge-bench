#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

#include "hlt.h"

/*
  MyCBot_v7 -> MyCBot_v8
  Improvements:
  - Stronger attack margin that scales with target production to avoid risky attacks.
  - Clear expansion scoring that prefers non-owned high-production weak tiles.
  - Harsher movement thresholds to avoid wasting strength.
*/

#define BOT_NAME "MyCBot_v8"

// Tunable parameters
#define ATTACK_MARGIN 5
#define ATTACK_PROD_WEIGHT 120
#define ATTACK_STR_WEIGHT 2

#define MOVE_PROD_MULT 2            // Require strength >= production * MOVE_PROD_MULT to consider moving
#define MIN_MOVE_STRENGTH 15

#define RANDOM_MOVE_THRESHOLD 120
#define RANDOM_MOVE_PROB 10

int main(void) {

    GAME game;
    int x, y;

    srand(time(NULL) ^ (getpid() << 16));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    SITE me = GetSiteFromXY(game, x, y);

                    // If no strength, stay to build
                    if (me.strength == 0) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }

                    // Find best attackable neighbor (non-owned and sufficiently weaker)
                    int best_attack_dir = STILL;
                    int best_attack_score = -1000000000;

                    // Find best expansion neighbor using a score that prefers non-owned high-production weak targets
                    int best_expand_dir = STILL;
                    int best_expand_score = -1000000000;

                    int dir;
                    for (dir = NORTH; dir <= WEST; dir++) {
                        SITE s = GetSiteFromMovement(game, x, y, dir);

                        // Compute a dynamic margin that grows with target production
                        int dynamic_margin = ATTACK_MARGIN + (s.production / 2);

                        if (s.owner != game.playertag) {
                            // Consider attack only if we have a safety margin over target
                            if (me.strength > s.strength + dynamic_margin) {
                                // score targets by their production and penalize strong targets
                                int score = s.production * ATTACK_PROD_WEIGHT - s.strength * ATTACK_STR_WEIGHT;
                                if (score > best_attack_score) {
                                    best_attack_score = score;
                                    best_attack_dir = dir;
                                }
                            }
                            // Expansion scoring: strongly prefer capturing non-owned tiles with high production and low strength
                            {
                                int score = s.production * 1000 - s.strength * 10;
                                if (score > best_expand_score) {
                                    best_expand_score = score;
                                    best_expand_dir = dir;
                                }
                            }
                        } else {
                            // Friendly neighbor - consider moving to consolidate only if safe (won't overflow 255)
                            if ((s.strength + me.strength) <= 255) {
                                // Friendly expansion score is lower priority than capturing non-owned tiles
                                int score = s.production * 100 - s.strength;
                                if (score > best_expand_score) {
                                    best_expand_score = score;
                                    best_expand_dir = dir;
                                }
                            }
                        }
                    }

                    // Prioritize attacking weaker non-owned neighbors
                    if (best_attack_dir != STILL) {
                        SetMove(game, x, y, best_attack_dir);
                        continue;
                    }

                    // Otherwise, if we have enough strength to move safely, move toward best expansion tile
                    if (best_expand_dir != STILL && best_expand_score > 0 && me.strength >= me.production * MOVE_PROD_MULT && me.strength > MIN_MOVE_STRENGTH) {
                        SetMove(game, x, y, best_expand_dir);
                        continue;
                    }

                    // Consolidation: if no expansion chosen, move toward stronger friendly neighbor to gather strength
                    if (best_expand_dir == STILL) {
                        int cons_dir = STILL;
                        int cons_strength = -1;
                        int d;
                        for (d = NORTH; d <= WEST; d++) {
                            SITE neigh = GetSiteFromMovement(game, x, y, d);
                            if (neigh.owner == game.playertag && neigh.strength > me.strength && (neigh.strength + me.strength) <= 255) {
                                if (neigh.strength > cons_strength) { cons_strength = neigh.strength; cons_dir = d; }
                            }
                        }
                        if (cons_dir != STILL) {
                            SetMove(game, x, y, cons_dir);
                            continue;
                        }
                    }

                    if (me.strength > RANDOM_MOVE_THRESHOLD) {
                        int r = rand() % 100;
                        if (r < RANDOM_MOVE_PROB) {
                            int rnd_dir = NORTH + (rand() % 4);
                            SetMove(game, x, y, rnd_dir);
                            continue;
                        }
                    }

                    // Default: stay to build up strength
                    SetMove(game, x, y, STILL);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}