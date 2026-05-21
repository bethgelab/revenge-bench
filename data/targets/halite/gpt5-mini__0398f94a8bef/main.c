#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <string.h>

#include "hlt.h"

#define BOT_NAME "MyCBot_v5"

int main(void) {

    GAME game;
    int x, y, direction;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        // Per-frame claimed target map stores accumulated committed strength.
        // flattened by (x * height + y)
        int total_cells = game.width * game.height;
        int *claimed = calloc(total_cells, sizeof(int));
        if (claimed == NULL) {
            // If allocation fails, proceed without coordination.
        }

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    SITE me = GetSiteFromXY(game, x, y);

                    // Dynamic threshold to decide whether to wait or act.
                    // Default slightly aggressive but can increase if enemies nearby.
                    int threshold = me.production * 6;
                    for (direction = NORTH; direction <= WEST; direction++) {
                        SITE n = GetSiteFromMovement(game, x, y, direction);
                        if (n.production > me.production) {
                            threshold = me.production * 3;
                        }
                        if (n.owner != 0 && n.owner != game.playertag) {
                            int more = me.production * 9;
                            if (more > threshold) threshold = more;
                        }
                    }

                    if (me.strength < threshold) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }

                    // Choose best adjacent target by score, but consider combined committed strength
                    // and potential friendly neighbors that could assist.
                    int best_dir = STILL;
                    int best_score = -1000000000;
                    int best_tx = -1, best_ty = -1;
                    for (direction = NORTH; direction <= WEST; direction++) {
                        SITE target = GetSiteFromMovement(game, x, y, direction);
                        int idx = target.x * game.height + target.y;
                        int claimed_str = (claimed ? claimed[idx] : 0);

                        // Estimate potential combined strength: claimed so far + our strength + nearby friendly neighbors (excluding ourselves)
                        int potential = claimed_str + me.strength;
                        if (target.owner != game.playertag) {
                            int d2;
                            for (d2 = NORTH; d2 <= WEST; d2++) {
                                SITE adj = GetSiteFromMovement(game, target.x, target.y, d2);
                                // skip adding our own cell (we already included me.strength)
                                if (adj.x == x && adj.y == y) continue;
                                if (adj.owner == game.playertag) potential += adj.strength;
                            }
                        }

                        // Only consider target if estimated potential can beat its strength
                        if (target.owner != game.playertag && potential > target.strength) {
                            // Score favors high-production, penalizes strong targets and already-claimed strength
                            int score = target.production * 12 - target.strength * 3 - claimed_str * 6;
                            if (target.owner == 0) score += 30; else score += 20;
                            // Slight tie-breaker: prefer closer (already adjacent) low-claimed targets by small bonus
                            if (claimed_str == 0) score += 5;
                            if (score > best_score) {
                                best_score = score;
                                best_dir = direction;
                                best_tx = target.x;
                                best_ty = target.y;
                            }
                        }
                    }

                    if (best_dir != STILL) {
                        // Commit our strength to the target so allies consider combined power.
                        if (claimed && best_tx >= 0 && best_ty >= 0) {
                            int idx = best_tx * game.height + best_ty;
                            int target_strength = GetSiteFromXY(game, best_tx, best_ty).strength;
                            int claimed_str = claimed[idx];
                            int needed = target_strength + 1 - claimed_str;
                            if (needed < 0) needed = 0;
                            int commit = me.strength;
                            if (commit > needed) commit = needed;
                            if (commit < 0) commit = 0;
                            claimed[idx] += commit;
                        }
                        SetMove(game, x, y, best_dir);
                    } else {
                        SetMove(game, x, y, STILL);
                    }
                }
            }
        }

        if (claimed) free(claimed);

        SendFrame(game);
    }

    return 0;
}