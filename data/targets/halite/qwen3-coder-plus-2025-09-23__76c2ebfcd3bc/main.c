#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int main() {
    srand(time(NULL));
    int n;
    scanf("%d", &n);

    for (int i = 0; i < n; i++) {
        int x;
        scanf("%d", &x);
        
        // If piece has low strength, stay still to accumulate more
        if (x < 5) {
            printf("0\n");
        } else {
            // Otherwise, move in a random direction to expand
            int move = rand() % 5;
            printf("%d\n", move);
        }
        fflush(stdout);
    }

    return 0;
}