#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <math.h>

#include "hlt.h"
#include <string.h>

// --- Data Structures for BFS ---
typedef struct {
    int x, y;
} Point;

typedef struct {
    Point *items;
    int front, rear, size, capacity;
} Queue;

Queue* createQueue(int capacity) {
    Queue* queue = (Queue*)malloc(sizeof(Queue));
    queue->capacity = capacity;
    queue->front = queue->size = 0;
    queue->rear = capacity - 1;
    queue->items = (Point*)malloc(queue->capacity * sizeof(Point));
    return queue;
}

int isQueueFull(Queue* queue) { return (queue->size == queue->capacity); }
int isQueueEmpty(Queue* queue) { return (queue->size == 0); }

void enqueue(Queue* queue, Point item) {
    if (isQueueFull(queue)) return;
    queue->rear = (queue->rear + 1) % queue->capacity;
    queue->items[queue->rear] = item;
    queue->size = queue->size + 1;
}

Point dequeue(Queue* queue) {
    Point item = queue->items[queue->front];
    queue->front = (queue->front + 1) % queue->capacity;
    queue->size = queue->size - 1;
    return item;
}

void freeQueue(Queue* queue) {
    free(queue->items);
    free(queue);
}

// --- Bot Logic ---

void shuffle(int *array, size_t n) {
    if (n > 1) {
        for (size_t i = 0; i < n - 1; i++) {
            size_t j = i + rand() / (RAND_MAX / (n - i) + 1);
            int t = array[j];
            array[j] = array[i];
            array[i] = t;
        }
    }
}

int get_combined_adjacent_enemy_strength(GAME game, int x, int y) {
    int combined_strength = 0;
    int directions[] = {NORTH, EAST, SOUTH, WEST};
    for (int i = 0; i < 4; i++) {
        int checkX = x, checkY = y;
        if (directions[i] == NORTH) checkY--; else if (directions[i] == EAST) checkX++;
        else if (directions[i] == SOUTH) checkY++; else if (directions[i] == WEST) checkX--;
        if (checkX >= 0 && checkX < game.width && checkY >= 0 && checkY < game.height &&
            game.owner[checkX][checkY] != 0 && game.owner[checkX][checkY] != game.playertag) {
            combined_strength += game.strength[checkX][checkY];
        }
    }
    return combined_strength;
}

int count_friendly_neighbors(GAME game, int targetX, int targetY, int attackerX, int attackerY) {
    int friend_count = 0;
    int directions[] = {NORTH, EAST, SOUTH, WEST};
    for (int i = 0; i < 4; i++) {
        int checkX = targetX, checkY = targetY;
        if (directions[i] == NORTH) checkY--; else if (directions[i] == EAST) checkX++;
        else if (directions[i] == SOUTH) checkY++; else if (directions[i] == WEST) checkX--;
        if (checkX == attackerX && checkY == attackerY) continue;
        if (checkX >= 0 && checkX < game.width && checkY >= 0 && checkY < game.height &&
            game.owner[checkX][checkY] == game.playertag) {
            friend_count++;
        }
    }
    return friend_count;
}

int is_border_square(GAME game, int x, int y) {
    int directions[] = {NORTH, EAST, SOUTH, WEST};
    for (int i = 0; i < 4; i++) {
        int checkX = x, checkY = y;
        if (directions[i] == NORTH) checkY--; else if (directions[i] == EAST) checkX++;
        else if (directions[i] == SOUTH) checkY++; else if (directions[i] == WEST) checkX--;
        if (checkX >= 0 && checkX < game.width && checkY >= 0 && checkY < game.height &&
            game.owner[checkX][checkY] != 0 && game.owner[checkX][checkY] != game.playertag) {
            return 1;
        }
    }
    return 0;
}

// BFS to find the direction towards the nearest border
int find_nearest_border_direction(GAME game, int startX, int startY) {
    int max_queue_size = game.width * game.height;
    Queue* queue = createQueue(max_queue_size);

    int visited[game.width][game.height];
    int parent_dir[game.width][game.height];
    for (int i = 0; i < game.width; i++) {
        for (int j = 0; j < game.height; j++) {
            visited[i][j] = 0;
            parent_dir[i][j] = 0;
        }
    }

    Point start = {startX, startY};
    enqueue(queue, start);
    visited[startX][startY] = 1;

    int target_direction = STILL;

    while (!isQueueEmpty(queue)) {
        Point current = dequeue(queue);

        if (is_border_square(game, current.x, current.y)) {
            // Found a border square, trace back to find the first step
            int traceX = current.x, traceY = current.y;
            while (parent_dir[traceX][traceY] != 0) {
                int dir = parent_dir[traceX][traceY];
                int prevX = traceX, prevY = traceY;
                if (dir == NORTH) prevY++; else if (dir == EAST) prevX--;
                else if (dir == SOUTH) prevY--; else if (dir == WEST) prevX++;
                
                if (prevX == startX && prevY == startY) {
                    target_direction = dir;
                    break;
                }
                traceX = prevX;
                traceY = prevY;
            }
            break; // Exit BFS
        }

        int directions[] = {NORTH, EAST, SOUTH, WEST};
        shuffle(directions, 4);
        for (int i = 0; i < 4; i++) {
            int d = directions[i];
            int newX = current.x, newY = current.y;
            if (d == NORTH) newY--; else if (d == EAST) newX++;
            else if (d == SOUTH) newY++; else if (d == WEST) newX--;

            if (newX >= 0 && newX < game.width && newY >= 0 && newY < game.height &&
                !visited[newX][newY] && game.owner[newX][newY] == game.playertag) {
                
                visited[newX][newY] = 1;
                parent_dir[newX][newY] = d;
                Point neighbor = {newX, newY};
                enqueue(queue, neighbor);
            }
        }
    }

    freeQueue(queue);
    return target_direction;
}


#define BOT_NAME "MyFlowBot"

int main(void) {
    GAME game;
    srand(time(NULL));
    game = GetInit();
    SendInit(BOT_NAME);

    int turn = 0;
    while (1) {
        GetFrame(game);
        turn++;

        for (int x = 0; x < game.width; x++) {
            for (int y = 0; y < game.height; y++) {
                if (game.owner[x][y] == game.playertag) {
                    int direction = STILL;
                    if ((turn < 50 && game.strength[x][y] > game.production[x][y] * 2) || (turn >= 50 && game.strength[x][y] > game.production[x][y] * 5) || game.strength[x][y] == 255) {
                        double best_score = -1.0;
                        int best_direction = STILL;
                        int directions[] = {NORTH, EAST, SOUTH, WEST};
                        shuffle(directions, 4);

                        for (int i = 0; i < 4; i++) {
                            int d = directions[i];
                            int newX = x, newY = y;
                            if (d == NORTH) newY--; else if (d == EAST) newX++;
                            else if (d == SOUTH) newY++; else if (d == WEST) newX--;

                            if (newX >= 0 && newX < game.width && newY >= 0 && newY < game.height) {
                                if (game.strength[x][y] <= get_combined_adjacent_enemy_strength(game, newX, newY)) continue;

                                double current_score = 0.0;
                                if (game.owner[newX][newY] != 0 && game.owner[newX][newY] != game.playertag) {
                                    if (game.strength[x][y] > game.strength[newX][newY]) {
                                        current_score = 1000.0 + game.production[newX][newY] * 10 + count_friendly_neighbors(game, newX, newY, x, y) * 50;
                                    }
                                } else if (game.owner[newX][newY] == 0) {
                                    if (game.production[newX][newY] > 0) {
                                        current_score = (double)game.production[newX][newY] / (game.strength[x][y] + 1.0);
                                        if (is_border_square(game, newX, newY)) current_score *= 2.0;
                                    }
                                }
                                if (current_score > best_score) {
                                    best_score = current_score;
                                    best_direction = d;
                                }
                            }
                        }
                        direction = best_direction;

                        if (direction == STILL) {
                            direction = find_nearest_border_direction(game, x, y);
                        }
                    }
                    SetMove(game, x, y, direction);
                }
            }
        }
        SendFrame(game);
    }
    return 0;
}