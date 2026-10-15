#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "StrategicBot_v4"

// Calculate the total strength of adjacent enemies
int getAdjacentEnemyStrength(GAME game, int x, int y) {
    int directions[] = {NORTH, EAST, SOUTH, WEST};
    int totalEnemyStrength = 0;
    SITE current = GetSiteFromXY(game, x, y);
    
    for (int i = 0; i < 4; i++) {
        SITE adjacent = GetSiteFromMovement(game, x, y, directions[i]);
        if (adjacent.owner != game.playertag && adjacent.owner != 0) {
            totalEnemyStrength += adjacent.strength;
        }
    }
    return totalEnemyStrength;
}

// Count how many of our pieces are adjacent
int getAdjacentFriendlyCount(GAME game, int x, int y) {
    int directions[] = {NORTH, EAST, SOUTH, WEST};
    int friendlyCount = 0;
    
    for (int i = 0; i < 4; i++) {
        SITE adjacent = GetSiteFromMovement(game, x, y, directions[i]);
        if (adjacent.owner == game.playertag) {
            friendlyCount++;
        }
    }
    return friendlyCount;
}

// Find the direction towards the best target with improved logic
int findBestDirection(GAME game, int x, int y) {
    int directions[] = {NORTH, EAST, SOUTH, WEST};
    int scores[4];
    int bestScore = -1000;
    SITE current = GetSiteFromXY(game, x, y);
    
    // Calculate scores for each direction
    for (int i = 0; i < 4; i++) {
        int dir = directions[i];
        SITE target = GetSiteFromMovement(game, x, y, dir);
        int score = 0;
        
        if (target.owner != game.playertag) {
            // Base score for expansion
            score += 120;
            
            // Heavily prefer high production areas
            score += target.production * 5;
            
            // Combat evaluation - prefer targets we can defeat
            if (current.strength > target.strength) {
                score += (current.strength - target.strength);
                // Bonus for easy victories
                if (current.strength > target.strength * 2) {
                    score += 50;
                }
            } else {
                // Penalty for attacking stronger targets
                score -= (target.strength - current.strength) * 2;
                // Heavy penalty if we're much weaker
                if (target.strength > current.strength * 1.5) {
                    score -= 200;
                }
            }
            
            // Prefer neutral over enemy (safer expansion)
            if (target.owner == 0) {
                score += 40;
            } else {
                // Enemy territory - consider if we have support
                int friendlySupport = getAdjacentFriendlyCount(game, target.x, target.y);
                score += friendlySupport * 20;
            }
            
            // Avoid low production areas unless they're very weak
            if (target.production <= 1 && target.strength > current.strength / 2) {
                score -= 30;
            }
            
        } else {
            // Moving to own territory - consolidation logic
            int combinedStrength = current.strength + target.strength;
            
            if (combinedStrength <= 255) {
                // Good consolidation
                score = target.production * 3 + 20;
                
                // Bonus if target is weak and we're strong
                if (target.strength < 50 && current.strength > 100) {
                    score += 30;
                }
            } else {
                // Strength would be wasted
                int waste = combinedStrength - 255;
                score = target.production * 2 - waste;
                
                // Heavy penalty for major waste
                if (waste > 50) {
                    score -= 100;
                }
            }
        }
        
        // Add small random factor for unpredictability
        score += (rand() % 15) - 7;
        
        scores[i] = score;
        if (score > bestScore) {
            bestScore = score;
        }
    }
    
    // Find all directions with good scores
    int goodDirections[4];
    int numGood = 0;
    int threshold = bestScore - 10; // Allow more variance
    
    for (int i = 0; i < 4; i++) {
        if (scores[i] >= threshold) {
            goodDirections[numGood++] = directions[i];
        }
    }
    
    // Randomly pick from good directions
    if (numGood > 0) {
        return goodDirections[rand() % numGood];
    }
    
    return STILL;
}

// Improved logic for when to stay still
int shouldStayStill(GAME game, int x, int y) {
    SITE current = GetSiteFromXY(game, x, y);
    
    // More aggressive expansion - lower threshold
    if (current.strength < current.production * 2) {
        return 1;
    }
    
    // Stay still if very close to cap and production is decent
    if (current.strength > 240 && current.production > 2) {
        return 1;
    }
    
    // Check threat level from adjacent enemies
    int adjacentEnemyStrength = getAdjacentEnemyStrength(game, x, y);
    int friendlySupport = getAdjacentFriendlyCount(game, x, y);
    
    // Stay if we're significantly outgunned and don't have support
    if (adjacentEnemyStrength > current.strength * 1.5 && friendlySupport < 2) {
        return 1;
    }
    
    // Stay if we're weak and surrounded by multiple enemies
    if (current.strength < 30 && adjacentEnemyStrength > 0) {
        int directions[] = {NORTH, EAST, SOUTH, WEST};
        int enemyCount = 0;
        for (int i = 0; i < 4; i++) {
            SITE adjacent = GetSiteFromMovement(game, x, y, directions[i]);
            if (adjacent.owner != game.playertag && adjacent.owner != 0) {
                enemyCount++;
            }
        }
        if (enemyCount >= 2) {
            return 1;
        }
    }
    
    return 0;
}

int main(void) {
    GAME game;
    int x, y, direction;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    
                    // Decide whether to stay still or move
                    if (shouldStayStill(game, x, y)) {
                        direction = STILL;
                    } else {
                        // Find the best direction to move
                        direction = findBestDirection(game, x, y);
                    }
                    
                    SetMove(game, x, y, direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}