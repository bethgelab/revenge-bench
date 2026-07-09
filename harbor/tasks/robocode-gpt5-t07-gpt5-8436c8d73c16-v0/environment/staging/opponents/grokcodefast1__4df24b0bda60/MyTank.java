package custom;

import robocode.AdvancedRobot;
import robocode.ScannedRobotEvent;
import robocode.HitWallEvent;
import robocode.HitRobotEvent;
import static robocode.util.Utils.normalRelativeAngleDegrees;

import java.awt.*;

public class MyTank extends AdvancedRobot {

    private double previousEnergy = 100;
    private int movementDirection = 1;
    private int gunDirection = 1;

    public void run() {
        setAdjustGunForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        setBodyColor(Color.red);
        setGunColor(Color.black);
        setRadarColor(Color.yellow);
        setScanColor(Color.green);

        while (true) {
            setTurnRadarRight(360);
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        double angleToEnemy = e.getBearing();

        // Radar lock
        double radarTurn = getHeading() - getRadarHeading() + e.getBearing();
        setTurnRadarRight(normalRelativeAngleDegrees(radarTurn));

        // Calculate enemy position
        double myX = getX();
        double myY = getY();
        double enemyX = myX + Math.sin(Math.toRadians(getHeading() + e.getBearing())) * e.getDistance();
        double enemyY = myY + Math.cos(Math.toRadians(getHeading() + e.getBearing())) * e.getDistance();

        // Adaptive firepower based on distance and energy change
        double changeInEnergy = previousEnergy - e.getEnergy();
        previousEnergy = e.getEnergy();
        double firePower = Math.min(3, Math.max(0.1, 400 / e.getDistance()));
        if (changeInEnergy > 0 && changeInEnergy <= 3) {
            firePower = changeInEnergy; // Fire the same as enemy
        }

        // Linear targeting
        double bulletSpeed = 20 - 3 * firePower;
        double enemyHeading = e.getHeadingRadians();
        double enemyVelocity = e.getVelocity();

        double predictedX = enemyX;
        double predictedY = enemyY;
        double deltaTime = 0;

        // Iterative prediction
        for (int i = 0; i < 10; i++) {
            double distance = Math.sqrt((predictedX - myX) * (predictedX - myX) + (predictedY - myY) * (predictedY - myY));
            deltaTime = distance / bulletSpeed;
            predictedX = enemyX + Math.sin(enemyHeading) * enemyVelocity * deltaTime;
            predictedY = enemyY + Math.cos(enemyHeading) * enemyVelocity * deltaTime;
        }

        double dx = predictedX - myX;
        double dy = predictedY - myY;
        double theta = Math.toDegrees(Math.atan2(dx, dy));
        double gunTurn = normalRelativeAngleDegrees(theta - getGunHeading());
        setTurnGunRight(gunTurn);

        setFire(firePower);

        // Anti-gravity movement: move towards center, repel from walls
        double centerX = getBattleFieldWidth() / 2.0;
        double centerY = getBattleFieldHeight() / 2.0;
        double forceX = centerX - myX;
        double forceY = centerY - myY;
        
        // Wall repulsion
        double wallMargin = 100;
        if (myX < wallMargin) forceX += 2000 / (wallMargin - myX + 1);
        if (myX > getBattleFieldWidth() - wallMargin) forceX -= 2000 / (myX - (getBattleFieldWidth() - wallMargin) + 1);
        if (myY < wallMargin) forceY += 2000 / (wallMargin - myY + 1);
        if (myY > getBattleFieldHeight() - wallMargin) forceY -= 2000 / (myY - (getBattleFieldHeight() - wallMargin) + 1);
        
        double angle = Math.toDegrees(Math.atan2(forceX, forceY));
        setTurnRight(normalRelativeAngleDegrees(angle - getHeading()));
        setAhead(50);

        execute();
    }

    public void onHitWall(HitWallEvent e) {
        // Reverse direction on hit wall
        setBack(50);
        execute();
    }

    public void onHitRobot(HitRobotEvent e) {
        double turnAngle = normalRelativeAngleDegrees(e.getBearing() + 180);
        setTurnRight(turnAngle);
        setBack(100);
        execute();
    }
}