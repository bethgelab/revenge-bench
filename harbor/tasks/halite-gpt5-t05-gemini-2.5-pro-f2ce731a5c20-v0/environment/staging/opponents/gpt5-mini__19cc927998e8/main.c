#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot-v2"

int main(void) {

    GAME game;
    int turn = 0;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {

        GetFrame(game);

        turn++;

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    SITE cur = GetSiteFromXY(game, x, y);

                    // If there's effectively no strength, stay (can't move)
                    if (cur.strength == 0) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }

                    // If strength is low compared to production, stay to build up.
                    int mult = (turn < 10) ? 3 : 2;
                    int threshold = cur.production * mult;
                    if (threshold < 5) threshold = 5; // slightly more permissive than before (was 6)
                    // If adjacent to enemies, be more aggressive: lower build threshold so frontline tiles act sooner
                    {
                        int enemy_adj = 0;
                        int sd2;
                        for (sd2 = NORTH; sd2 <= WEST; sd2++) {
                            SITE s_check = GetSiteFromMovement(game, x, y, sd2);
                            if (s_check.owner != 0 && s_check.owner != game.playertag) enemy_adj++;
                        }
                        if (enemy_adj > 0) {
                            threshold -= cur.production; /* be more willing to move/attack on the frontline */
                            if (threshold < 5) threshold = 5;
                        }
                    }
                    if (cur.strength < threshold) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }

                    // Try coordinated attack: consider sum of nearby owned strengths.
                    int attacked = 0;
                    int bestDir = STILL;
                    SITE bestNeighbor;
                    bestNeighbor.production = -1000;
                    bestNeighbor.owner = -1; // ensure initialized for comparison
                    bestNeighbor.strength = 0;
                    int d;
                    for (d = NORTH; d <= WEST; d++) {
                        SITE n = GetSiteFromMovement(game, x, y, d);
                        if (n.owner != game.playertag) {
                            int combined = cur.strength;
                            int sd;
                            for (sd = NORTH; sd <= WEST; sd++) {
                                SITE s = GetSiteFromMovement(game, x, y, sd);
                                if (s.owner == game.playertag && sd != d) {
                                    /* Count only a portion of adjacent allies to avoid overcommit */
                                    combined += s.strength / 2;
                                }
                            }
                            /* Attack if combined strength likely to overcome neighbor (with margin) */
                            int margin = (n.owner == 0) ? 3 : 6;
                            if (combined > n.strength + margin) {
                                SetMove(game, x, y, d);
                                attacked = 1;
                                break;
                            }
                            /* Additional aggressive rule: if neighbor is neutral and weak relative to this tile, try to take it
                               Helps early expansion into weak neutral cells even if allies are not perfectly positioned. */
                            if (n.owner == 0 && n.strength < cur.strength + 10 && turn < 80) {
                                SetMove(game, x, y, d);
                                attacked = 1;
                                break;
                            }
                        }
                        /* Track neighbor with highest production to expand towards */
                        int nscore = n.production + (n.owner==0 ? 2 : 0) - (n.strength/10);
                        int bscore = bestNeighbor.production + (bestNeighbor.owner==0 ? 2 : 0) - (bestNeighbor.strength/10);
                        if (nscore > bscore || (nscore == bscore && (rand() % 2))) {
                            bestNeighbor = n;
                            bestDir = d;
                        }
                    }

                    if (attacked) continue;

                    // If no good attack, move toward the best production neighbor (or stay)
                    if (bestDir != STILL) {
                        // Safety: ensure moving into non-owned neighbor has sufficient combined support
                        if (bestNeighbor.owner != game.playertag) {
                            int combined2 = cur.strength;
                            int sd;
                            for (sd = NORTH; sd <= WEST; sd++) {
                                SITE s2 = GetSiteFromMovement(game, x, y, sd);
                                if (s2.owner == game.playertag && sd != bestDir) {
                                    combined2 += s2.strength / 2;
                                }
                            }
                            int margin2 = (bestNeighbor.owner == 0) ? 3 : 6;
                            if (combined2 <= bestNeighbor.strength + margin2) {
                                SetMove(game, x, y, STILL);
                                continue;
                            }
                        }
                        // if best neighbor has lower production than current, and we're not very strong, stay to build
                        if (bestNeighbor.production < cur.production && cur.strength < cur.production * 3 + 8) {
                            SetMove(game, x, y, STILL);
                        } else {
                            // Safety: avoid overfilling an owned tile (wasteful because strength caps at 255)
                            if (bestNeighbor.owner == game.playertag) {
                                if (cur.strength + bestNeighbor.strength > 255) {
                                    // prefer to stay rather than move and waste strength
                                    SetMove(game, x, y, STILL);
                                } else {
                                    SetMove(game, x, y, bestDir);
                                }
                            } else {
                                SetMove(game, x, y, bestDir);
                            }
                        }
                    } else {
                        SetMove(game, x, y, STILL);
                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}