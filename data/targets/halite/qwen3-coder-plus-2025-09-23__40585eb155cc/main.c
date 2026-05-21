#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define MIN(a, b) ((a) < (b) ? (a) : (b))

// Directions: 0=stay, 1=N, 2=E, 3=S, 4=W
int dr[] = {0, -1, 0, 1, 0};  // row offset for directions
int dc[] = {0, 0, 1, 0, -1}; // col offset for directions

int main() {
    int n;
    scanf("%d", &n);
    
    int *map = malloc(n * n * sizeof(int));
    int *prod = malloc(n * n * sizeof(int));
    int *strength = malloc(n * n * sizeof(int));
    
    // Seed random number generator
    srand(time(NULL));
    
    while (1) {
        int player_tag;
        scanf("%d", &player_tag);
        
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                scanf("%d %d %d", &map[i * n + j], &prod[i * n + j], &strength[i * n + j]);
            }
        }
        
        // Process each cell
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                int cell_type = map[i * n + j];
                int cell_prod = prod[i * n + j];
                int cell_str = strength[i * n + j];
                
                if (cell_type == player_tag && cell_str > 1) {
                    // Our cell with strength > 1 - consider moving
                    int best_direction = 0; // default: stay
                    int best_score = -1;
                    
                    // Check adjacent cells for potential moves
                    for (int dir = 1; dir <= 4; dir++) {
                        int ni = i + dr[dir];
                        int nj = j + dc[dir];
                        
                        // Check if the adjacent cell is within bounds
                        if (ni >= 0 && ni < n && nj >= 0 && nj < n) {
                            int adj_type = map[ni * n + nj];
                            int adj_str = strength[ni * n + nj];
                            
                            // Calculate score for this move
                            int score = 0;
                            
                            if (adj_type == 0) {
                                // Neutral cell - high priority
                                score = 100 + cell_prod; // Prioritize high-production neutral cells
                            } else if (adj_type != player_tag) {
                                // Enemy cell - consider attacking if we can win
                                if (cell_str > adj_str) {
                                    score = 50; // Attack if we can win
                                } else {
                                    score = -10; // Don't attack if we'll lose
                                }
                            } else {
                                // Our own cell - generally avoid unless part of coordinated move
                                score = 10; // Could be useful for consolidation
                            }
                            
                            // Prefer moves that don't leave us with very weak cells
                            if (cell_str <= 3) {
                                score -= 20; // Discourage moving from weak cells
                            }
                            
                            if (score > best_score) {
                                best_score = score;
                                best_direction = dir;
                            }
                        }
                    }
                    
                    // Only move if we found a beneficial move
                    if (best_score > 0) {
                        printf("%d %d %d\n", i, j, best_direction);
                    } else {
                        printf("%d %d 0\n", i, j); // Stay put
                    }
                } else if (cell_type == player_tag) {
                    // Our cell with strength <= 1 - definitely stay to accumulate
                    printf("%d %d 0\n", i, j);
                }
            }
        }
        printf("NO MORE\n");
        fflush(stdout);
    }
    
    free(map);
    free(prod);
    free(strength);
    return 0;
}