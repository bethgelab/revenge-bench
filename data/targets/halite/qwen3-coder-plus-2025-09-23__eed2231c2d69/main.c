#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
    int n;
    scanf("%d", &n);

    int map[n][n];
    int prod[n][n];

    int i, j;
    for (i = 0; i < n; i++) {
        for (j = 0; j < n; j++) {
            scanf("%d", &map[i][j]);
        }
    }

    for (i = 0; i < n; i++) {
        for (j = 0; j < n; j++) {
            scanf("%d", &prod[i][j]);
        }
    }

    int num_moving_pieces;
    scanf("%d", &num_moving_pieces);

    int moving_pieces[num_moving_pieces][4];
    for (i = 0; i < num_moving_pieces; i++) {
        for (j = 0; j < 4; j++) {
            scanf("%d", &moving_pieces[i][j]);
        }
    }

    // Define directions: 0=stay, 1=up, 2=right, 3=down, 4=left
    int dx[5] = {0, -1, 0, 1, 0};  // Change in row
    int dy[5] = {0, 0, 1, 0, -1};  // Change in col

    for (i = 0; i < n; i++) {
        for (j = 0; j < n; j++) {
            if (map[i][j] > 0) {  // If this is our piece (positive value means owned by us)
                int direction = 0; // Default: stay
                
                // Only move pieces with strength > 1 to avoid losing territory unnecessarily
                if (map[i][j] > 1) {
                    int best_dir = 0;
                    int best_score = -1;
                    
                    // Evaluate each direction
                    for (int dir = 1; dir <= 4; dir++) {
                        int ni = i + dx[dir];
                        int nj = j + dy[dir];
                        
                        // Check if the new position is within bounds
                        if (ni >= 0 && ni < n && nj >= 0 && nj < n) {
                            // Score based on what's in the target cell
                            int score = 0;
                            
                            if (map[ni][nj] == 0) {  // Neutral territory
                                score = prod[ni][nj] + 10;  // High value for neutral cells
                            } else if (map[ni][nj] < 0) {  // Enemy territory
                                // Only attack if we can win (our strength > enemy strength)
                                int enemy_strength = -map[ni][nj];
                                if (map[i][j] > enemy_strength) {
                                    score = prod[ni][nj] + 5;  // Medium value for attackable enemies
                                }
                            } else {  // Our own territory
                                // Consolidate with our pieces that have low strength
                                score = 2;  // Low value
                            }
                            
                            if (score > best_score) {
                                best_score = score;
                                best_dir = dir;
                            }
                        }
                    }
                    
                    direction = best_dir;
                }
                
                printf("%d %d %d\n", i, j, direction);
            }
        }
    }

    fflush(stdout);
    return 0;
}