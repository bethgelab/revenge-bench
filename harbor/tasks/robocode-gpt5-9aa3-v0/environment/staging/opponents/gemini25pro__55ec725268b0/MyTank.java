package custom;

import robocode.*;
import java.awt.Color;
import java.awt.geom.Point2D;

public class MyTank extends AdvancedRobot {

    private ScannedRobotEvent lastScannedRobotEvent;
    private static double lateralDirection = 1;
    private static double lastEnemyVelocity = 0;

    public void run() {
        setBodyColor(new Color(0, 200, 0));
        setGunColor(new Color(0, 150, 50));
        setRadarColor(new Color(0, 100, 100));
        setBulletColor(new Color(255, 255, 100));
        setScanColor(new Color(255, 200, 200));

        setAdjustGunForRobotTurn(true);
        setAdjustRadarForRobotTurn(true);
        setAdjustRadarForGunTurn(true);

        while (true) {
            if (getRadarTurnRemaining() == 0.0) {
                setTurnRadarRightRadians(Double.POSITIVE_INFINITY);
            }
            execute();
        }
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        // Radar lock
        double radarTurn = getHeadingRadians() + e.getBearingRadians() - getRadarHeadingRadians();
        setTurnRadarRightRadians(robocode.util.Utils.normalRelativeAngle(radarTurn));

        // Predictive targeting
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        double enemyX = getX() + e.getDistance() * Math.sin(absoluteBearing);
        double enemyY = getY() + e.getDistance() * Math.cos(absoluteBearing);
        double enemyHeading = e.getHeadingRadians();
        double enemyVelocity = e.getVelocity();
        
        double enemyTurnRate = 0.0;
        if (lastScannedRobotEvent != null) {
            double timeDiff = getTime() - lastScannedRobotEvent.getTime();
            if (timeDiff > 0) {
                enemyTurnRate = (e.getHeadingRadians() - lastScannedRobotEvent.getHeadingRadians()) / timeDiff;
            }
        }
        
        double firepower = Math.min(400 / e.getDistance(), 3);
        // Simple Energy Management
        // Close-range firing adjustment

        // Aggressive close-range combat when we have energy
        if (e.getDistance() < 150 && getEnergy() > 50) {
            firepower = 3.0;
        }

        // Conserve energy when we are low, or the enemy is low
        if (getEnergy() < 25 || e.getEnergy() < 10) {
            firepower = Math.min(firepower, 1.0);
        }

        // If we have a big energy lead, press the advantage
        if (getEnergy() > e.getEnergy() + 50) {
            firepower = Math.min(firepower + 0.5, 3.0);
        }

        // Suicidal check: never fire more than we have. Leave a tiny bit for movement.
        if (firepower >= getEnergy()) {
            firepower = getEnergy() - 0.1;
        }
        double bulletSpeed = 20 - firepower * 3;
        double deltaTime = 0;
        double predictedX = enemyX, predictedY = enemyY;
        while((++deltaTime) * bulletSpeed < Point2D.distance(getX(), getY(), predictedX, predictedY)){		
            predictedX += Math.sin(enemyHeading) * enemyVelocity;
            predictedY += Math.cos(enemyHeading) * enemyVelocity;
            enemyHeading += enemyTurnRate;
            if(	predictedX < 18.0 || predictedY < 18.0
                || predictedX > getBattleFieldWidth() - 18.0
                || predictedY > getBattleFieldHeight() - 18.0){
                predictedX = Math.min(Math.max(18.0, predictedX), getBattleFieldWidth() - 18.0);
                predictedY = Math.min(Math.max(18.0, predictedY), getBattleFieldHeight() - 18.0);
                break;
            }
        }
        
        double theta = robocode.util.Utils.normalAbsoluteAngle(Math.atan2(predictedX - getX(), predictedY - getY()));
        setTurnGunRightRadians(robocode.util.Utils.normalRelativeAngle(theta - getGunHeadingRadians()));

        // Firing logic
        if (getGunHeat() == 0 && Math.abs(getGunTurnRemaining()) < 0.5) {
            setFire(firepower);
        }
        
        doMovement(e);
        
        lastScannedRobotEvent = e;
    }

    void doMovement(ScannedRobotEvent e) {
        double absoluteBearing = getHeadingRadians() + e.getBearingRadians();
        double distance = e.getDistance();

        double x = getX();
        double y = getY();
        double battleFieldWidth = getBattleFieldWidth();
        double battleFieldHeight = getBattleFieldHeight();

        double forceX = 0, forceY = 0;

        // Gravitational force towards the enemy - stronger as we get closer
        double G = 1000;
        double gravity = G / Math.pow(distance, 2);
        forceX += gravity * Math.sin(absoluteBearing);
        forceY += gravity * Math.cos(absoluteBearing);

        // Wall repulsion forces - very strong if we are close to a wall
        double W = 15000;
        forceX -= W / Math.pow(x, 3);
        forceX += W / Math.pow(battleFieldWidth - x, 3);
        forceY -= W / Math.pow(y, 3);
        forceY += W / Math.pow(battleFieldHeight - y, 3);

        // The angle of the net force
        double forceAngle = Math.atan2(forceY, forceX);

        // Our target heading is perpendicular to the force angle, to orbit the enemy
        double desiredDistance = 250;
        double distanceError = distance - desiredDistance;
        double adjustment = Math.atan(distanceError / 100.0);
        double targetHeading = forceAngle + (lateralDirection * (Math.PI / 2)) + adjustment;

        double turn = robocode.util.Utils.normalRelativeAngle(targetHeading - getHeadingRadians());
        setTurnRightRadians(turn);
        setAhead(150);

        // Switch circling direction if the enemy slows down significantly
        if (Math.abs(e.getVelocity()) < Math.abs(lastEnemyVelocity) - 1.5) {
            lateralDirection *= -1;
        }
        lastEnemyVelocity = e.getVelocity();
    }

    public void onHitByBullet(HitByBulletEvent e) {
        lateralDirection *= -1;
    }

    public void onHitWall(HitWallEvent e) {
        lateralDirection *= -1;
    }
}