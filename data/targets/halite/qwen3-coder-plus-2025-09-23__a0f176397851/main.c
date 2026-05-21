#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define MAX(a, b) ((a) > (b) ? (a) : (b))

int main() {
    int n, i, j, k;
    scanf("%d", &n);

    int* map = (int*)malloc(n * n * sizeof(int));
    int* prod = (int*)malloc(n * n * sizeof(int));

    for (i = 0; i < n; i++) {
        for (j = 0; j < n; j++) {
            scanf("%d", &map[i * n + j]);
        }
    }

    for (i = 0; i < n; i++) {
        for (j = 0; j < n; j++) {
            scanf("%d", &prod[i * n + j]);
        }
    }

    srand(time(NULL));

    // Count our pieces
    int moves = 0;
    for (i = 0; i < n; i++) {
        for (j = 0; j < n; j++) {
            if (map[i * n + j] > 0) {
                moves++;
            }
        }
    }

    printf("%d\n", moves);

    // For each of our pieces, decide where to move
    for (i = 0; i < n; i++) {
        for (j = 0; j < n; j++) {
            if (map[i * n + j] > 0) {
                int x = i;
                int y = j;
                
                // Look for the best adjacent cell to move to
                // Prioritize: 1) Unowned cells with high production
                //            2) Enemy cells we can conquer
                //            3) Stay if no good options
                
                int best_dir = 0; // 0 = stay, 1 = up, 2 = down, 3 = left, 4 = right
                int best_score = -1;
                
                // Check staying in place
                if (map[x * n + y] > best_score) {
                    best_score = map[x * n + y];
                    best_dir = 0;
                }
                
                // Check up (x-1, y)
                if (x > 0) {
                    int target_idx = (x-1) * n + y;
                    int score = 0;
                    
                    if (map[target_idx] == 0) {
                        // Neutral cell - prioritize by production
                        score = prod[target_idx] * 10 + 50; // High value for neutral high-production cells
                    } else if (map[target_idx] < 0) {
                        // Enemy cell - consider if we can conquer it
                        int our_strength = map[x * n + y];
                        int enemy_strength = -map[target_idx];
                        if (our_strength > enemy_strength) {
                            score = 30; // Value for conquering enemy
                        }
                    } else {
                        // Friendly cell - consolidate if needed
                        score = 10;
                    }
                    
                    if (score > best_score) {
                        best_score = score;
                        best_dir = 1;
                    }
                }
                
                // Check down (x+1, y)
                if (x < n-1) {
                    int target_idx = (x+1) * n + y;
                    int score = 0;
                    
                    if (map[target_idx] == 0) {
                        // Neutral cell - prioritize by production
                        score = prod[target_idx] * 10 + 50;
                    } else if (map[target_idx] < 0) {
                        // Enemy cell - consider if we can conquer it
                        int our_strength = map[x * n + y];
                        int enemy_strength = -map[target_idx];
                        if (our_strength > enemy_strength) {
                            score = 30;
                        }
                    } else {
                        // Friendly cell - consolidate if needed
                        score = 10;
                    }
                    
                    if (score > best_score) {
                        best_score = score;
                        best_dir = 2;
                    }
                }
                
                // Check left (x, y-1)
                if (y > 0) {
                    int target_idx = x * n + (y-1);
                    int score = 0;
                    
                    if (map[target_idx] == 0) {
                        // Neutral cell - prioritize by production
                        score = prod[target_idx] * 10 + 50;
                    } else if (map[target_idx] < 0) {
                        // Enemy cell - consider if we can conquer it
                        int our_strength = map[x * n + y];
                        int enemy_strength = -map[target_idx];
                        if (our_strength > enemy_strength) {
                            score = 30;
                        }
                    } else {
                        // Friendly cell - consolidate if needed
                        score = 10;
                    }
                    
                    if (score > best_score) {
                        best_score = score;
                        best_dir = 3;
                    }
                }
                
                // Check right (x, y+1)
                if (y < n-1) {
                    int target_idx = x * n + (y+1);
                    int score = 0;
                    
                    if (map[target_idx] == 0) {
                        // Neutral cell - prioritize by production
                        score = prod[target_idx] * 10 + 50;
                    } else if (map[target_idx] < 0) {
                        // Enemy cell - consider if we can conquer it
                        int our_strength = map[x * n + y];
                        int enemy_strength = -map[target_idx];
                        if (our_strength > enemy_strength) {
                            score = 30;
                        }
                    } else {
                        // Friendly cell - consolidate if needed
                        score = 10;
                    }
                    
                    if (score > best_score) {
                        best_score = score;
                        best_dir = 4;
                    }
                }
                
                // Calculate destination based on best direction
                int dx = x, dy = y;
                
                if (best_dir == 1) dx = x - 1;  // up
                else if (best_dir == 2) dx = x + 1;  // down
                else if (best_dir == 3) dy = y - 1;  // left
                else if (best_dir == 4) dy = y + 1;  // right
                // if best_dir == 0, stay in place (dx = x, dy = y)
                
                printf("%d %d %d %d\n", x, y, dx, dy);
            }
        }
    }

    fflush(stdout);

    free(map);
    free(prod);

    return 0;
}