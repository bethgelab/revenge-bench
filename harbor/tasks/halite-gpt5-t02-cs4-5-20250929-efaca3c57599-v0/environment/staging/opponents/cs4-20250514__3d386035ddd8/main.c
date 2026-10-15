#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "SmartBot_v6"

int main(void) {
    GAME game;
    int x, y, direction;
    SITE current_site, target_site;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    current_site = GetSiteFromXY(game, x, y);
                    
                    // If strength is low, stay still to build up
                    if (current_site.strength < current_site.production * 5) {
                        SetMove(game, x, y, STILL);
                        continue;
                    }
                    
                    // Look for best direction to expand
                    int best_direction = STILL;
                    int best_score = -1000;
                    
                    for (direction = 1; direction <= 4; direction++) {
                        target_site = GetSiteFromMovement(game, x, y, direction);
                        
                        int score = 0;
                        
                        // Prefer neutral territory
                        if (target_site.owner == 0) {
                            score += 100;
                            // Prefer high production sites
                            score += target_site.production * 10;
                            // Prefer weak sites we can capture
                            score -= target_site.strength;
                        }
                        // Avoid enemy territory unless we're much stronger
                        else if (target_site.owner != game.playertag) {
                            if (current_site.strength > target_site.strength + 50) {
                                score += 50;
                            } else {
                                score -= 200;
                            }
                        }
                        // Combine with friendly pieces if they're weak
                        else if (target_site.owner == game.playertag) {
                            if (target_site.strength < 100) {
                                score += 30;
                            } else {
                                score -= 50; // Avoid overcrowding
                            }
                        }
                        
                        if (score > best_score) {
                            best_score = score;
                            best_direction = direction;
                        }
                    }
                    
                    // Only move if we found a good direction
                    if (best_score > 0) {
                        SetMove(game, x, y, best_direction);
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