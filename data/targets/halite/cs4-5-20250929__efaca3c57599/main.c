#include <stdio.h>
#include <stdlib.h>

#include "hlt.h"

#define BOT_NAME "ImprovedBot"

int is_border(GAME game, int x, int y) {
    // Check if any adjacent cell is not owned by us
    SITE north = GetSiteFromMovement(game, x, y, NORTH);
    SITE east = GetSiteFromMovement(game, x, y, EAST);
    SITE south = GetSiteFromMovement(game, x, y, SOUTH);
    SITE west = GetSiteFromMovement(game, x, y, WEST);
    
    return (north.owner != game.playertag || 
            east.owner != game.playertag || 
            south.owner != game.playertag || 
            west.owner != game.playertag);
}

int get_move(GAME game, int x, int y) {
    SITE site = GetSiteFromXY(game, x, y);
    
    // Don't move if we have no strength
    if (site.strength == 0) {
        return STILL;
    }
    
    // Check if we're at a border
    if (is_border(game, x, y)) {
        // Try to attack a weak adjacent square
        SITE north = GetSiteFromMovement(game, x, y, NORTH);
        SITE east = GetSiteFromMovement(game, x, y, EAST);
        SITE south = GetSiteFromMovement(game, x, y, SOUTH);
        SITE west = GetSiteFromMovement(game, x, y, WEST);
        
        // Attack if we can win
        if (north.owner != game.playertag && site.strength > north.strength) {
            return NORTH;
        }
        if (east.owner != game.playertag && site.strength > east.strength) {
            return EAST;
        }
        if (south.owner != game.playertag && site.strength > south.strength) {
            return SOUTH;
        }
        if (west.owner != game.playertag && site.strength > west.strength) {
            return WEST;
        }
        
        // If we can't attack, wait until we have enough strength
        return STILL;
    }
    
    // We're in interior - move toward border if we have enough strength
    if (site.strength < site.production * 5) {
        return STILL;
    }
    
    // Move north or west to get to border
    // Prefer the direction that gets us closer to a border
    SITE north = GetSiteFromMovement(game, x, y, NORTH);
    SITE west = GetSiteFromMovement(game, x, y, WEST);
    
    // If north is not ours, we're at north border, try west
    if (north.owner != game.playertag) {
        if (west.owner != game.playertag) {
            // Both are borders, prefer NORTH
            return NORTH;
        }
        return WEST;
    }
    
    // If west is not ours, we're at west border, go north
    if (west.owner != game.playertag) {
        return NORTH;
    }
    
    // Both north and west are ours, prefer north
    return NORTH;
}

int main(void) {
    GAME game;
    int x, y;


    game = GetInit();
    SendInit(BOT_NAME);

    while (1) {
        GetFrame(game);

        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    int direction = get_move(game, x, y);
                    SetMove(game, x, y, direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}