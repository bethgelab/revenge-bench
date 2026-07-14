#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "hlt.h"

#define BOT_NAME "MyCBot"

int main(void) {
    int turn = 0;

    GAME game;
    int x, y;

    srand(time(NULL));

    game = GetInit();
    SendInit(BOT_NAME);
    int map_size = game.width * game.height;


    while (1) {
        turn++;

        GetFrame(game);

        for (x = 0 ; x < game.width ; x++) {
            for (y = 0 ; y < game.height ; y++) {
                if (game.owner[x][y] == game.playertag) {
                    // Find nearest friendly piece
                    int nearest_x = -1, nearest_y = -1;
                    int min_dist = 9999;
                    for(int nx = 0; nx < game.width; nx++) {
                        for(int ny = 0; ny < game.height; ny++) {
                            if(game.owner[nx][ny] == game.playertag && !(nx == x && ny == y)) {
                                int dist = abs(nx - x) + abs(ny - y);
                                if(dist < min_dist) {
                                    min_dist = dist;
                                    nearest_x = nx;
                                    nearest_y = ny;
                                }
                            }
                        }
                    }
                    // Determine group direction
                    int group_dir = -1;
                    if(nearest_x != -1) {
                        int dx = nearest_x - x;
                        int dy = nearest_y - y;
                        if(abs(dx) > abs(dy)) {
                            if(dx > 0) group_dir = 1; // EAST
                            else if(dx < 0) group_dir = 3; // WEST
                        } else if(abs(dy) > abs(dx)) {
                            if(dy > 0) group_dir = 2; // SOUTH
                            else if(dy < 0) group_dir = 0; // NORTH
                        } else {
                            // Tie, prioritize dx then dy
                            if(dx > 0) group_dir = 1;
                            else if(dx < 0) group_dir = 3;
                            else if(dy > 0) group_dir = 2;
                            else if(dy < 0) group_dir = 0;
                        }
                    }

                    int best_direction = 4; // STILL
                    int max_score = -1;
                    int best_dirs[5];
                    int num_best = 0;
                    for(int d = 0; d < 5; d++){
                        SITE target = GetSiteFromMovement(game, x, y, d);
                        int score = 0;
                        if(d == 4){ // STILL
                            score = game.production[x][y];
                            if(game.strength[x][y] < 50) score += 20;
                        } else if(target.owner != game.playertag && game.strength[x][y] > target.strength + 10 && (target.owner == 0 || game.strength[x][y] - target.strength > 60)){
                            score = target.production + 20;
                        }
                        // Add grouping bonus
                        int base_bonus = (turn < 100) ? 15 : (turn < 200) ? 10 : 5;
                        int group_bonus = base_bonus + (map_size > 1600 ? (map_size - 1600) / 200 : 0);
                        if(d == group_dir && min_dist <= 10) score += group_bonus;
                        if(d == 4 && min_dist > 10) score += 10;
                        // Enemy threat penalty
                        int enemy_threat = 0;
                        for(int ex = 0; ex < game.width; ex++){
                            for(int ey = 0; ey < game.height; ey++){
                                if(game.owner[ex][ey] != game.playertag && game.owner[ex][ey] != 0){
                                    int dx = abs(ex - target.x);
                                    int dy = abs(ey - target.y);
                                    if(dx > game.width / 2) dx = game.width - dx;
                                    if(dy > game.height / 2) dy = game.height - dy;
                                    int dist = dx + dy;
                                    if(dist <= 2) enemy_threat += game.strength[ex][ey];
                                }
                            }
                        }
                        score -= enemy_threat / 20;
                        if(score > max_score){
                            max_score = score;
                            num_best = 1;
                            best_dirs[0] = d;
                        } else if(score == max_score){
                            best_dirs[num_best++] = d;
                        }
                    }
                    best_direction = best_dirs[rand() % num_best];
                    SetMove(game, x, y, best_direction);
                }
            }
        }

        SendFrame(game);
    }

    return 0;
}