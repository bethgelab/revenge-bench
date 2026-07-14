package custom;

import robocode.*;
import java.awt.Color;

public class MyTank extends AdvancedRobot {
    
    public void run() {
        setBodyColor(Color.blue);
        setGunColor(Color.red);
        setRadarColor(Color.green);
        
        while (true) {
            ahead(100);
            turnGunRight(360);
            back(100);
            turnGunRight(360);
        }
    }
    
    public void onScannedRobot(ScannedRobotEvent e) {
        fire(1);
    }
    
    public void onHitByBullet(HitByBulletEvent e) {
        turnLeft(90 - e.getBearing());
    }
    
    public void onHitWall(HitWallEvent e) {
        back(20);
        turnRight(90);
    }
}