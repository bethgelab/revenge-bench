package custom;
import java.util.*;

import robocode.Robot;
import robocode.ScannedRobotEvent;
import robocode.HitWallEvent;
import robocode.HitRobotEvent;
import robocode.HitByBulletEvent;

import java.awt.*;

public class MyTank extends Robot {

    private HashMap<String, Object[]> enemyData = new HashMap<>();

    public void run() {
        setBodyColor(Color.red);
        setGunColor(Color.black);
        setRadarColor(Color.yellow);
        setBulletColor(Color.green);
        setScanColor(Color.green);
        setAdjustRadarForRobotTurn(true);
        setAdjustGunForRobotTurn(true);

        while(true) {
            // Anti-gravity movement: attract to center, repel from walls
            double centerX = getBattleFieldWidth() / 2.0;
            double centerY = getBattleFieldHeight() / 2.0;
            double forceX = (centerX - getX()) * 0.01; // attraction to center
            double forceY = (centerY - getY()) * 0.01;

            // Repel from walls
            if (getX() < 100) forceX += 1000 / (getX() + 1);
            if (getX() > getBattleFieldWidth() - 100) forceX -= 1000 / (getBattleFieldWidth() - getX() + 1);
            if (getY() < 100) forceY += 1000 / (getY() + 1);
            if (getY() > getBattleFieldHeight() - 100) forceY -= 1000 / (getBattleFieldHeight() - getY() + 1);

            double angle = Math.toDegrees(Math.atan2(forceX, forceY));
            double turn = angle - getHeading();
            turnRight(turn);
            ahead(50);

            turnRadarRight(360);
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        double distance = e.getDistance();
        double power = Math.min(getEnergy() / 10, Math.min(3, 400 / distance)); // More power for closer enemies
        double bulletSpeed = 20 - 3 * power;
        double time = distance / bulletSpeed;

        // Calculate enemy position
        double enemyX = getX() + Math.sin(Math.toRadians(getHeading() + e.getBearing())) * distance;
        double enemyY = getY() + Math.cos(Math.toRadians(getHeading() + e.getBearing())) * distance;

        Object[] prevData = enemyData.get(e.getName());
        double accel = 0;
        if (prevData != null && getTime() > (Double) prevData[4]) {
            double deltaTime = getTime() - (Double) prevData[4];
            accel = (e.getVelocity() - (Double) prevData[2]) / deltaTime;
        }

        // Iterative predictive targeting
        double futureX = enemyX;
        double futureY = enemyY;
        double bulletTime = time;
        for(int i = 0; i < 5; i++) {
            double predictedVelocity = e.getVelocity() + accel * bulletTime;
            futureX = enemyX + Math.sin(Math.toRadians(e.getHeading())) * (e.getVelocity() * bulletTime + 0.5 * accel * bulletTime * bulletTime);
            futureY = enemyY + Math.cos(Math.toRadians(e.getHeading())) * (e.getVelocity() * bulletTime + 0.5 * accel * bulletTime * bulletTime);
            double distToTarget = Math.sqrt((futureX - getX())*(futureX - getX()) + (futureY - getY())*(futureY - getY()));
            bulletTime = distToTarget / bulletSpeed;
        }
        double deltaX = futureX - getX();
        double deltaY = futureY - getY();
        double futureBearing = Math.toDegrees(Math.atan2(deltaX, deltaY));

        // Turn gun to future bearing
        double gunTurn = futureBearing - getGunHeading();
        if (distance < 100 || e.getVelocity() < 2) {
            turnGunRight(e.getBearing());
        } else {
            turnGunRight(gunTurn);
        }

        fire(power);
        double radarTurn = e.getBearing() - getRadarHeading() + 10;
        turnRadarRight(radarTurn);
        if (getEnergy() > e.getEnergy() && distance < 150) {
            ahead(50);
        }
        if (distance < 200) {
            turnRight(180);
            ahead(100);
        }
        // Move away if too close

        // Update enemy data
        enemyData.put(e.getName(), new Object[]{enemyX, enemyY, e.getVelocity(), e.getHeading(), (double) getTime()});
    }

    public void onHitWall(HitWallEvent e) {
        back(20);
        double dodgeAngle = e.getBearing() + (Math.random() > 0.5 ? 90 : -90);
        turnRight(dodgeAngle);
    }

    public void onHitRobot(HitRobotEvent e) {
        back(50);
    }

    public void onHitByBullet(HitByBulletEvent e) {
        double dodgeAngle = e.getBearing() + (Math.random() > 0.5 ? 90 : -90);
        turnRight(dodgeAngle);
        ahead(50);
    }
}