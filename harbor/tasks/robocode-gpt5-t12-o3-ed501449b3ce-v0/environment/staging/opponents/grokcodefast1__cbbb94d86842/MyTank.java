package custom;

import robocode.AdvancedRobot;
import robocode.ScannedRobotEvent;
import robocode.HitByBulletEvent;
import java.awt.*;
import java.util.*;
import java.util.Random;

public class MyTank extends AdvancedRobot {
    private Random random = new Random();
    private Map<String, ScannedRobotEvent> enemies = new HashMap<>();

    public void run() {
        setBodyColor(Color.BLUE);
        setGunColor(Color.RED);
        setRadarColor(Color.GREEN);
        setTurnRadarRight(360); // Spin radar for continuous scanning

        // Infinite loop for movement
        while (true) {
            // Anti-gravity: move towards center
            double centerX = getBattleFieldWidth() / 2;
            double centerY = getBattleFieldHeight() / 2;
            double deltaX = centerX - getX();
            double deltaY = centerY - getY();
            double angleToCenter = Math.toDegrees(Math.atan2(deltaX, deltaY));
            double turn = angleToCenter - getHeading() + (random.nextDouble() - 0.5) * 20;
            // Normalize turn
            while (turn > 180) turn -= 360;
            while (turn < -180) turn += 360;

            double ahead = 100 + random.nextInt(100);
            if (wouldHitWall(ahead)) {
                setAhead(50);
                setTurnRight(random.nextInt(180) - 90);
            } else {
                setAhead(ahead);
                setTurnRight(turn);
            }
            execute();
        }
    }

    private boolean wouldHitWall(double distance) {
        double angle = Math.toRadians(getHeading());
        double nextX = getX() + Math.sin(angle) * distance;
        double nextY = getY() + Math.cos(angle) * distance;
        return nextX < 0 || nextX > getBattleFieldWidth() || nextY < 0 || nextY > getBattleFieldHeight();
    }

    public void onScannedRobot(ScannedRobotEvent e) {
        enemies.put(e.getName(), e);
        
        ScannedRobotEvent target = null;
        double minScore = Double.MAX_VALUE;
        for (ScannedRobotEvent sre : enemies.values()) {
            double score = sre.getEnergy() / sre.getDistance();
            if (score < minScore) {
                minScore = score;
                target = sre;
            }
        }
        if (target == null) return;
        
        double bearing = target.getBearing();
        double distance = target.getDistance();
        double enemyHeading = target.getHeading();
        double enemyVelocity = target.getVelocity();
        double firePower = Math.min(3, 400 / distance);
        double bulletSpeed = 20 - 3 * firePower;
        double time = distance / bulletSpeed;

        // Current enemy position
        double myX = getX();
        double myY = getY();
        double myHeading = getHeading();
        double enemyX = myX + distance * Math.sin(Math.toRadians(myHeading + bearing));
        double enemyY = myY + distance * Math.cos(Math.toRadians(myHeading + bearing));

        // Predictive position
        double futureX = enemyX + enemyVelocity * time * Math.sin(Math.toRadians(enemyHeading));
        double futureY = enemyY + enemyVelocity * time * Math.cos(Math.toRadians(enemyHeading));

        // Angle to predicted position
        double deltaX = futureX - myX;
        double deltaY = futureY - myY;
        double futureBearing = Math.toDegrees(Math.atan2(deltaX, deltaY)) - myHeading;

        // Normalize bearing
        while (futureBearing > 180) futureBearing -= 360;
        while (futureBearing < -180) futureBearing += 360;

        setTurnGunRight(futureBearing);
        if (getEnergy() > firePower * 10) {
            setFire(firePower);
        }
        execute();
    }

    public void onHitByBullet(HitByBulletEvent e) {
        int direction = random.nextBoolean() ? 90 : -90;
        setTurnRight(direction);
        setAhead(50 + random.nextInt(50));
        execute();
    }
}