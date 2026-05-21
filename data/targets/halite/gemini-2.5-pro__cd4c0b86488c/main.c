#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <stdbool.h>

#include "hlt.h"

#define BOT_NAME "MyCBotV14"
#define MAX_TURNS 200

// For the BFS
typedef struct {
    int x, y, direction;
} BFS_Q_ITEM;

int find_nearest_border_direction(int x, int y, GAME game);
int find_nearest_weak_border_direction(int start_x, int start_y, GAME game, float avg_border_strength);
bool is_border_piece(int x, int y, GAME game);

bool is_border_piece(int x, int y, GAME game) {
    if (GetSiteFromMovement(game, x, y, NORTH).owner != game.playertag) return true;
    if (GetSiteFromMovement(game, x, y, EAST).owner != game.playertag) return true;
    if (GetSiteFromMovement(game, x, y, SOUTH).owner != game.playertag) return true;
    if (GetSiteFromMovement(game, x, y, WEST).owner != game.playertag) return true;
    return false;
}

int main(void) {

    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);

    int turn = 0;
    while (1) {
        turn++;

        GetFrame(game);

        // Calculate average strength of friendly border pieces
        long total_border_strength = 0;
        int border_piece_count = 0;
        for (int bx = 0; bx < game.width; bx++) {
            for (int by = 0; by < game.height; by++) {
                if (game.owner[bx][by] == game.playertag && is_border_piece(bx, by, game)) {
                    total_border_strength += game.strength[bx][by];
                    border_piece_count++;
                }
            }
        }
        float avg_border_strength = 0;
        if (border_piece_count > 0) {
            avg_border_strength = (float)total_border_strength / border_piece_count;
        }


        for (x = 0; x < game.width; x++) {
            for (y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                        float strength_multiplier = 3.0 + (turn / (float)MAX_TURNS) * 5.0;
                        if (game.strength[x][y] > game.production[x][y] * strength_multiplier) {
                        
                        bool isBorderPiece = is_border_piece(x, y, game);

                        if (isBorderPiece) {
                            // Logic for border pieces: attack weakest adjacent enemy with overkill prevention
                            int bestDirection = STILL;
                            int minStrength = 256;
                            int directions[] = {NORTH, EAST, SOUTH, WEST};
                            for (int i = 0; i < 4; i++) {
                                int d = directions[i];
                                SITE neighbor = GetSiteFromMovement(game, x, y, d);

                                if (neighbor.owner != game.playertag && game.strength[x][y] > neighbor.strength) {
                                    // This is a potential target
                                    bool is_overkill = (neighbor.owner != 0 && game.strength[x][y] > neighbor.strength + 50);
                                    
                                    if (!is_overkill && neighbor.strength < minStrength) {
                                        minStrength = neighbor.strength;
                                        bestDirection = d;
                                    }
                                }
                            }
                            
                            // If a good attack was found, execute it.
                            // Otherwise, move towards the nearest enemy/neutral border to prevent getting stuck.
                            if (bestDirection != STILL) {
                                SetMove(game, x, y, bestDirection);
                            } else {
                                int move = find_nearest_border_direction(x, y, game);
                                SetMove(game, x, y, move);
                            }

                        } else {
                            // Interior piece: move to reinforce the nearest weak friendly border piece
                            int move = find_nearest_weak_border_direction(x, y, game, avg_border_strength);
                            if (move != STILL) {
                                SetMove(game, x, y, move);
                            } else {
                                // Fallback: if no weak friendly border piece is found, move to any border
                                move = find_nearest_border_direction(x, y, game);
                                SetMove(game, x, y, move);
                            }
                        }

                    }
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}

// This function finds the nearest non-friendly square. Used by stagnant border pieces and as a fallback.
int find_nearest_border_direction(int start_x, int start_y, GAME game) {
    int q_size = game.width * game.height;
    BFS_Q_ITEM* queue = malloc(q_size * sizeof(BFS_Q_ITEM));
    int head = 0, tail = 0;

    bool** visited = malloc(game.width * sizeof(bool*));
    for(int i = 0; i < game.width; i++) {
        visited[i] = calloc(game.height, sizeof(bool));
    }

    visited[start_x][start_y] = true;

    int directions[] = {NORTH, EAST, SOUTH, WEST};
    for (int i = 0; i < 4; i++) {
        int d = directions[i];
        SITE neighbor = GetSiteFromMovement(game, start_x, start_y, d);
        if (!visited[neighbor.x][neighbor.y]) {
            if (neighbor.owner != game.playertag) { // Target condition
                free(queue);
                for(int j = 0; j < game.width; j++) free(visited[j]);
                free(visited);
                return d;
            }
            visited[neighbor.x][neighbor.y] = true;
            queue[tail++] = (BFS_Q_ITEM){neighbor.x, neighbor.y, d};
        }
    }

    while(head < tail) {
        BFS_Q_ITEM current = queue[head++];

        for (int i = 0; i < 4; i++) {
            int d = directions[i];
            SITE neighbor = GetSiteFromMovement(game, current.x, current.y, d);
            if (!visited[neighbor.x][neighbor.y]) {
                if (neighbor.owner != game.playertag) { // Target condition
                    int result_direction = current.direction;
                    free(queue);
                    for(int j = 0; j < game.width; j++) free(visited[j]);
                    free(visited);
                    return result_direction;
                }
                visited[neighbor.x][neighbor.y] = true;
                queue[tail++] = (BFS_Q_ITEM){neighbor.x, neighbor.y, current.direction};
            }
        }
    }
    
    free(queue);
    for(int i = 0; i < game.width; i++) free(visited[i]);
    free(visited);
    return STILL;
}

// This function finds the nearest friendly border piece that is weaker than average.
int find_nearest_weak_border_direction(int start_x, int start_y, GAME game, float avg_border_strength) {
    if (avg_border_strength == 0) return STILL; // No border pieces to move towards

    int q_size = game.width * game.height;
    BFS_Q_ITEM* queue = malloc(q_size * sizeof(BFS_Q_ITEM));
    int head = 0, tail = 0;

    bool** visited = malloc(game.width * sizeof(bool*));
    for(int i = 0; i < game.width; i++) {
        visited[i] = calloc(game.height, sizeof(bool));
    }

    visited[start_x][start_y] = true;

    int directions[] = {NORTH, EAST, SOUTH, WEST};
    for (int i = 0; i < 4; i++) {
        int d = directions[i];
        SITE neighbor = GetSiteFromMovement(game, start_x, start_y, d);
        if (!visited[neighbor.x][neighbor.y]) {
            // Target condition
            if (neighbor.owner == game.playertag && is_border_piece(neighbor.x, neighbor.y, game) && game.strength[neighbor.x][neighbor.y] < avg_border_strength) {
                free(queue);
                for(int j = 0; j < game.width; j++) free(visited[j]);
                free(visited);
                return d;
            }
            visited[neighbor.x][neighbor.y] = true;
            queue[tail++] = (BFS_Q_ITEM){neighbor.x, neighbor.y, d};
        }
    }

    while(head < tail) {
        BFS_Q_ITEM current = queue[head++];

        for (int i = 0; i < 4; i++) {
            int d = directions[i];
            SITE neighbor = GetSiteFromMovement(game, current.x, current.y, d);
            if (!visited[neighbor.x][neighbor.y]) {
                // Target condition
                if (neighbor.owner == game.playertag && is_border_piece(neighbor.x, neighbor.y, game) && game.strength[neighbor.x][neighbor.y] < avg_border_strength) {
                    int result_direction = current.direction;
                    free(queue);
                    for(int j = 0; j < game.width; j++) free(visited[j]);
                    free(visited);
                    return result_direction;
                }
                visited[neighbor.x][neighbor.y] = true;
                queue[tail++] = (BFS_Q_ITEM){neighbor.x, neighbor.y, current.direction};
            }
        }
    }
    
    free(queue);
    for(int i = 0; i < game.width; i++) free(visited[i]);
    free(visited);
    return STILL; // No weak border piece found
}