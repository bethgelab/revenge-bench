#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define STILL 0
#define NORTH 1
#define EAST 2
#define SOUTH 3
#define WEST 4

int main() {
    int width, height;
    scanf("%d %d", &width, &height);

    int **production = malloc(height * sizeof(int*));
    for (int i = 0; i < height; i++) {
        production[i] = malloc(width * sizeof(int));
        for (int j = 0; j < width; j++) {
            scanf("%d", &production[i][j]);
        }
    }

    while (1) {
        int n;
        scanf("%d", &n);

        // Read player information
        int player_id, num_players;
        scanf("%d %d", &num_players, &player_id);

        // Read the entire board state
        // The board is represented as [player][y][x] where player is the player index
        int ***board = malloc(num_players * sizeof(int**));
        for (int p = 0; p < num_players; p++) {
            board[p] = malloc(height * sizeof(int*));
            for (int i = 0; i < height; i++) {
                board[p][i] = malloc(width * sizeof(int));
                for (int j = 0; j < width; j++) {
                    scanf("%d", &board[p][i][j]);
                }
            }
        }

        // Read my pieces
        int *x_coords = malloc(n * sizeof(int));
        int *y_coords = malloc(n * sizeof(int));
        int *strengths = malloc(n * sizeof(int));
        for (int i = 0; i < n; i++) {
            scanf("%d %d %d", &x_coords[i], &y_coords[i], &strengths[i]);
        }

        // Make decisions for each piece
        for (int i = 0; i < n; i++) {
            int x = x_coords[i];
            int y = y_coords[i];
            int strength = strengths[i];

            // Improved strategy: 
            // 1. If adjacent to enemy with sufficient strength, attack
            // 2. Otherwise, move toward high production uncontrolled cells
            // 3. If no good moves, stay still
            
            int best_direction = STILL;
            int best_value = -1;
            
            // Check adjacent cells for potential moves
            int dx[5] = {0, 0, 1, 0, -1}; // STILL, NORTH, EAST, SOUTH, WEST
            int dy[5] = {0, -1, 0, 1, 0};
            
            for (int dir = 0; dir <= 4; dir++) {
                int new_x = x + dx[dir];
                int new_y = y + dy[dir];
                
                // Check bounds
                if (new_x < 0 || new_x >= width || new_y < 0 || new_y >= height) {
                    continue;
                }
                
                // Determine who controls this cell and with what strength
                int cell_owner = -1;
                int cell_strength = 0;
                
                for (int p = 0; p < num_players; p++) {
                    if (board[p][new_y][new_x] > 0) {
                        cell_owner = p;
                        cell_strength = board[p][new_y][new_x];
                        break;
                    }
                }
                
                // If it's an enemy cell and we can beat it
                if (cell_owner != -1 && cell_owner != player_id && strength > cell_strength) {
                    // Attack!
                    best_direction = dir;
                    break; // Attack immediately if possible
                }
                
                // If it's an uncontrolled (neutral) cell
                if (cell_owner == -1) {
                    // Prefer high production cells that we can take
                    int value = production[new_y][new_x] * 2; // Weight production heavily
                    
                    if (value > best_value) {
                        best_value = value;
                        best_direction = dir;
                    }
                }
                
                // If it's our own cell, consider consolidating
                if (cell_owner == player_id && dir != STILL) {
                    // Consolidate to high production cells or to strengthen defenses
                    int value = production[new_y][new_x];
                    
                    if (value > best_value) {
                        best_value = value;
                        best_direction = dir;
                    }
                }
            }

            printf("%d %d %d\n", x, y, best_direction);
            fflush(stdout);
        }

        // Free memory for next turn
        for (int p = 0; p < num_players; p++) {
            for (int i = 0; i < height; i++) {
                free(board[p][i]);
            }
            free(board[p]);
        }
        free(board);
        free(x_coords);
        free(y_coords);
        free(strengths);
    }

    // Free production array at the end (though we'll never reach here in infinite loop)
    for (int i = 0; i < height; i++) {
        free(production[i]);
    }
    free(production);

    return 0;
}